import http.server
import os
import re
import socket
import ssl
import subprocess
import threading

import pytest

MULTIPART_NAME_RE = re.compile(rb'Content-Disposition: form-data; name="([^"]+)"')


class RequestRecord:
    '''What a fixture server saw for a single request.'''

    def __init__(self, method, path, headers):
        self.method = method
        self.path = path
        self.headers = headers
        self.body_bytes_read = 0
        self.multipart_names = set()

    @property
    def authorization(self):
        return self.headers.get('Authorization')

    def scan_multipart_names(self, chunk):
        '''Collect multipart field names out of a body chunk.

        Only the names matter here, so this reads the Content-Disposition lines
        as they stream past instead of buffering megabytes to parse properly.
        A name split across a chunk boundary would be missed, but the parts
        under test sit in the first few kilobytes.
        '''
        for match in MULTIPART_NAME_RE.finditer(chunk):
            self.multipart_names.add(match.group(1).decode('latin-1'))


class RecordingServer:
    '''Plain-HTTP fixture that records every request and replies per a script.

    ``responses`` maps ``(method, path_prefix)`` to ``(status, body)``. The
    first matching entry wins; anything unmatched gets a 404.
    '''

    def __init__(self, responses):
        self.responses = responses
        self.requests = []
        self._lock = threading.Lock()
        self._httpd = None
        self._thread = None

    def _match(self, method, path):
        for (m, prefix), response in self.responses.items():
            if m == method and path.startswith(prefix):
                return response
        return (404, b'"not found"')

    def start(self):
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def _handle(self):
                record = RequestRecord(self.command, self.path, dict(self.headers))
                with server._lock:
                    server.requests.append(record)

                status, body = server._match(self.command, self.path)

                # Read the body so the client can finish writing; record how
                # much actually got consumed.
                length = int(self.headers.get('Content-Length') or 0)
                remaining = length
                tail = b''
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, 65536))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    record.body_bytes_read += len(chunk)
                    # Overlap chunks so a header split across the boundary is
                    # still seen.
                    record.scan_multipart_names(tail + chunk)
                    tail = chunk[-256:]

                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('x-total', '0')
                self.end_headers()
                self.wfile.write(body)

            do_GET = _handle
            do_POST = _handle
            do_DELETE = _handle

        # Port 0 lets the OS pick a free port; no fixed ports, no collisions.
        self._httpd = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        return self

    @property
    def url(self):
        host, port = self._httpd.server_address[:2]
        return f'http://{host}:{port}/chester/api'

    def stop(self):
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def requests_for(self, method):
        with self._lock:
            return [r for r in self.requests if r.method == method]


class AbortingTLSServer:
    '''TLS fixture that reads only the headers, replies 401, then hangs up.

    This reproduces the server-side behaviour the fix is about: the handler
    rejects the token before touching the body, and the connection dies while
    the client is still streaming its multipart payload.
    '''

    def __init__(self, certfile, keyfile, preflight_status=200):
        self.certfile = certfile
        self.keyfile = keyfile
        self.preflight_status = preflight_status
        self.requests = []
        self._lock = threading.Lock()
        self._sock = None
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(('127.0.0.1', 0))
        self._sock.listen(8)
        self._sock.settimeout(0.5)

        self._context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self._context.load_cert_chain(self.certfile, self.keyfile)

        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return self

    def _serve(self):
        while not self._stop.is_set():
            try:
                raw, _ = self._sock.accept()
            except (socket.timeout, OSError):
                continue
            threading.Thread(target=self._handle, args=(raw,), daemon=True).start()

    def _handle(self, raw):
        conn = None
        try:
            conn = self._context.wrap_socket(raw, server_side=True)
            conn.settimeout(5)

            # Read request line + headers only, never the body.
            buf = b''
            while b'\r\n\r\n' not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    return
                buf += chunk

            head = buf.split(b'\r\n\r\n', 1)[0].decode('latin-1')
            lines = head.split('\r\n')
            method, path = lines[0].split(' ')[:2]
            headers = {}
            for line in lines[1:]:
                if ':' in line:
                    k, v = line.split(':', 1)
                    headers[k.strip()] = v.strip()

            record = RequestRecord(method, path, headers)
            record.body_bytes_read = len(buf.split(b'\r\n\r\n', 1)[1])
            with self._lock:
                self.requests.append(record)

            if method == 'POST':
                # The case under test: reply 401 without draining the body,
                # then close hard while the client is still writing.
                body = b'"unauthorized"'
                head = (
                    'HTTP/1.1 401 Unauthorized\r\n'
                    'Content-Type: application/json\r\n'
                    f'Content-Length: {len(body)}\r\n'
                    'Connection: close\r\n\r\n'
                )
                conn.sendall(head.encode() + body)
                conn.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER,
                                b'\x01\x00\x00\x00\x00\x00\x00\x00')
                conn.close()
                conn = None
                return

            body = b'[]' if self.preflight_status == 200 else b'"unauthorized"'
            reason = 'OK' if self.preflight_status == 200 else 'Unauthorized'
            head = (
                f'HTTP/1.1 {self.preflight_status} {reason}\r\n'
                'Content-Type: application/json\r\n'
                f'Content-Length: {len(body)}\r\n'
                'x-total: 0\r\n'
                'Connection: close\r\n\r\n'
            )
            conn.sendall(head.encode() + body)
        except (ssl.SSLError, OSError):
            pass
        finally:
            if conn is not None:
                try:
                    conn.close()
                except OSError:
                    pass

    @property
    def url(self):
        host, port = self._sock.getsockname()[:2]
        return f'https://{host}:{port}/chester/api'

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        if self._sock is not None:
            self._sock.close()

    def requests_for(self, method):
        with self._lock:
            return [r for r in self.requests if r.method == method]


@pytest.fixture
def http_server():
    def factory(responses):
        server = RecordingServer(responses).start()
        servers.append(server)
        return server

    servers = []
    yield factory
    for server in servers:
        server.stop()


@pytest.fixture(scope='session')
def tls_cert(tmp_path_factory):
    '''Self-signed cert for 127.0.0.1, generated once per session.'''
    directory = tmp_path_factory.mktemp('tls')
    certfile = directory / 'cert.pem'
    keyfile = directory / 'key.pem'

    subprocess.run(
        ['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
         '-keyout', str(keyfile), '-out', str(certfile),
         '-days', '1', '-subj', '/CN=127.0.0.1',
         '-addext', 'subjectAltName=IP:127.0.0.1'],
        check=True, capture_output=True,
    )
    return str(certfile), str(keyfile)


@pytest.fixture
def tls_server(tls_cert):
    def factory(preflight_status=200):
        certfile, keyfile = tls_cert
        server = AbortingTLSServer(certfile, keyfile, preflight_status).start()
        servers.append(server)
        return server

    servers = []
    yield factory
    for server in servers:
        server.stop()


@pytest.fixture
def app_dir(tmp_path):
    '''A build tree the upload command accepts, with a multi-MB hex payload.

    Generated in memory rather than committed: the point is only to exceed
    socket buffers so the write side fails. A zephyr.elf is present so tests
    can tell whether the upload picks it up.
    '''
    zephyr = tmp_path / 'build' / 'zephyr'
    zephyr.mkdir(parents=True)
    (zephyr / 'merged.hex').write_bytes(os.urandom(4 * 1024 * 1024))
    (zephyr / 'zephyr.elf').write_bytes(os.urandom(1024 * 1024))
    return tmp_path
