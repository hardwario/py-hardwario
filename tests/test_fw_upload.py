'''Tests for `hardwario chester app fw upload` error reporting.

The bug: the server validates the token before reading the body, so an invalid
token closes the connection mid-upload. requests then surfaces SSLEOFError and
"Max retries exceeded" while the real 401 never reaches the user.

Assertions are on exit code and stderr, never on exception classes -- which
exception wins the race (SSLEOFError / ConnectionResetError / BrokenPipeError)
depends on timing and platform.
'''

import os
import subprocess
import sys
from pathlib import Path

import pytest

TOKEN = 'test-token-value'

# The installed console script, i.e. exactly what a user runs.
HARDWARIO_BIN = str(Path(sys.executable).parent / 'hardwario')


def run_cli(args, app_dir, token=None, ca_bundle=None, extra_env=None):
    '''Invoke the real CLI in a subprocess.

    hardwario.cli:main wraps the click group in a plain function, so click's
    CliRunner cannot invoke it -- subprocess is the only faithful path.
    '''
    env = dict(os.environ)
    # Never let a developer's real .env or shell leak into a test.
    env.pop('HARDWARIO_CLOUD_TOKEN', None)
    env.pop('HARDWARIO_FW_API_URL', None)
    if token is not None:
        env['HARDWARIO_CLOUD_TOKEN'] = token
    if ca_bundle is not None:
        env['REQUESTS_CA_BUNDLE'] = ca_bundle
    if extra_env:
        env.update(extra_env)

    return subprocess.run(
        [HARDWARIO_BIN] + args,
        cwd=str(app_dir), env=env, capture_output=True, text=True, timeout=120,
    )


def upload_args(url):
    return ['chester', 'app', 'fw', '--url', url, 'upload',
            '--name', 'test-app', '--version', 'v1.0.0']


def test_invalid_token_fails_preflight_without_sending_payload(http_server, app_dir):
    '''An invalid token must be caught before the multipart POST is sent.'''
    server = http_server({('GET', '/chester/api/v1/firmware'): (401, b'"unauthorized"')})

    result = run_cli(upload_args(server.url), app_dir, token='bad-token')

    assert result.returncode != 0
    assert 'HARDWARIO_CLOUD_TOKEN' in result.stderr
    # The whole point: no 21 MB body goes out on a token we already know is bad.
    assert server.requests_for('POST') == []


def test_invalid_token_message_explains_likely_causes(http_server, app_dir):
    server = http_server({('GET', '/chester/api/v1/firmware'): (401, b'"unauthorized"')})

    result = run_cli(upload_args(server.url), app_dir, token='bad-token')

    stderr = result.stderr.lower()
    assert 'expired' in stderr
    assert 'rotated' in stderr or 'revoked' in stderr


def test_token_whitespace_is_stripped_from_header(http_server, app_dir):
    '''A token pasted with a trailing newline must not corrupt the header.'''
    server = http_server({
        ('GET', '/chester/api/v1/firmware'): (200, b'[]'),
        ('POST', '/chester/api/v1/firmware'): (201, b'{"id": "abc123"}'),
    })

    result = run_cli(upload_args(server.url), app_dir, token=f'  {TOKEN}\n')

    assert result.returncode == 0, result.stderr
    assert server.requests
    for record in server.requests:
        value = record.authorization
        assert value == f'Bearer {TOKEN}'
        assert '\n' not in value and '\r' not in value
        assert value == value.strip()


@pytest.mark.parametrize('token', ['', '   ', '\n'])
def test_empty_token_fails_before_any_network_call(http_server, app_dir, token):
    '''No token means no request at all, and a message that says which knob to turn.

    A literally empty value is caught by click's own `required=` handling
    ("Missing option '--token'"); whitespace-only reaches our code and must be
    rejected there. Either way the user is told what to set and nothing is sent.
    '''
    server = http_server({('GET', '/chester/api/v1/firmware'): (200, b'[]')})

    result = run_cli(upload_args(server.url), app_dir, token=token)

    assert result.returncode != 0
    assert 'HARDWARIO_CLOUD_TOKEN' in result.stderr or '--token' in result.stderr
    assert server.requests == []


def test_connection_closed_mid_upload_is_translated(tls_server, app_dir, tls_cert):
    '''Preflight passes, then the server hangs up mid-write.

    The user must get an actionable message -- not SSLEOFError, not
    "Max retries exceeded", not a traceback.
    '''
    certfile, _ = tls_cert
    server = tls_server(preflight_status=200)

    result = run_cli(upload_args(server.url), app_dir, token=TOKEN, ca_bundle=certfile)

    assert result.returncode != 0
    assert 'Traceback' not in result.stderr
    assert 'SSLEOFError' not in result.stderr
    assert 'Max retries exceeded' not in result.stderr
    assert 'upload' in result.stderr.lower()


def test_upload_is_not_retried(tls_server, app_dir, tls_cert):
    '''Retrying a 21 MB non-idempotent POST wastes minutes and hides the cause.'''
    certfile, _ = tls_cert
    server = tls_server(preflight_status=200)

    result = run_cli(upload_args(server.url), app_dir, token=TOKEN, ca_bundle=certfile)

    assert result.returncode != 0
    assert len(server.requests_for('POST')) == 1


def test_zephyr_elf_is_not_sent_by_default(http_server, app_dir):
    '''The ELF holds debug symbols and source paths, so it is opt-in.

    app_dir puts a zephyr.elf in the build tree, which the upload used to pick
    up automatically. Assert on the multipart part names the server actually
    received rather than on payload size, which the hex dominates anyway.
    '''
    server = http_server({
        ('GET', '/chester/api/v1/firmware'): (200, b'[]'),
        ('POST', '/chester/api/v1/firmware'): (201, b'{"id": "abc123"}'),
    })

    result = run_cli(upload_args(server.url), app_dir, token=TOKEN)

    assert result.returncode == 0, result.stderr
    post = server.requests_for('POST')[0]
    assert 'firmware_hex' in post.multipart_names
    assert 'zephyr_elf' not in post.multipart_names
    assert 'zephyr_elf_sha256' not in post.multipart_names


def test_zephyr_elf_is_sent_with_the_flag(http_server, app_dir):
    server = http_server({
        ('GET', '/chester/api/v1/firmware'): (200, b'[]'),
        ('POST', '/chester/api/v1/firmware'): (201, b'{"id": "abc123"}'),
    })

    result = run_cli(upload_args(server.url) + ['--zephyr-elf'], app_dir, token=TOKEN)

    assert result.returncode == 0, result.stderr
    post = server.requests_for('POST')[0]
    assert 'zephyr_elf' in post.multipart_names
    assert 'zephyr_elf_sha256' in post.multipart_names


def test_successful_upload_is_unchanged(http_server, app_dir):
    server = http_server({
        ('GET', '/chester/api/v1/firmware'): (200, b'[]'),
        ('POST', '/chester/api/v1/firmware'): (201, b'{"id": "abc123"}'),
    })

    result = run_cli(upload_args(server.url), app_dir, token=TOKEN)

    assert result.returncode == 0, result.stderr
    assert 'abc123' in result.stdout
    posts = server.requests_for('POST')
    assert len(posts) == 1
    # The payload really did go out.
    assert posts[0].body_bytes_read > 1024 * 1024
