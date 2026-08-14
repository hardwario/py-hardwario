import requests
import subprocess
import glob
import os
from requests.adapters import HTTPAdapter
from loguru import logger
from hardwario.chester.utils import find_hex, find_manifest_json, find_zephyr_elf, test_file
from hardwario.common.utils import get_file_hash

# DEFAULT_API_URL = 'http://0.0.0.0:4000/chester/api'
DEFAULT_API_URL = 'https://firmware.hardwario.com/chester/api'


class FirmwareApiException(Exception):
    pass


class FirmwareApi:

    def __init__(self, url=DEFAULT_API_URL, token=None):
        self._headers = {}
        self._url = url
        # A token of '' or whitespace must not silently fall through to an
        # unauthenticated request; set_token rejects it with a clear message.
        if token is not None:
            self.set_token(token)

    @property
    def url(self):
        return self._url

    def set_token(self, token):
        # Tokens are copy-pasted or read out of a file, so a trailing newline is
        # routine. requests rejects a header value containing one with a message
        # that says nothing about which token is at fault.
        token = (token or '').strip()
        if not token:
            raise FirmwareApiException(
                'API token is empty. Set HARDWARIO_CLOUD_TOKEN or pass --token. '
                'Get one at https://legacy.hardwario.cloud .')
        self._headers['Authorization'] = 'Bearer ' + token

    def request(self, method, url, **kwargs):
        url = self._url + url
        logger.debug('{} {}', url, kwargs)
        try:
            self._response = requests.request(
                method, url, headers=self._headers, **kwargs)
        except ConnectionError:
            raise FirmwareApiException('Cannot connect to cloud service')

        if 200 < self._response.status_code >= 300:
            text = self._response.text.strip('"')
            raise FirmwareApiException(f'{self._response.status_code}: {text}')

        return self._response.json()

    def check_token(self):
        '''Reject a bad token before a multipart upload is streamed.

        The server authenticates before reading the request body. On a bad token
        it answers 401 and returns without draining it, so the connection dies
        mid-write and the client sees a TLS EOF instead of the 401. A cheap
        authenticated GET first means the user gets the real reason.
        '''
        try:
            response = requests.get(
                self._url + '/v1/firmware', headers=self._headers,
                params={'offset': 0, 'limit': 1}, timeout=30)
        except requests.exceptions.RequestException as e:
            raise FirmwareApiException(f'Cannot connect to cloud service: {e}') from e

        if response.status_code in (401, 403):
            raise FirmwareApiException(
                'API token was rejected by the cloud service (HTTP '
                f'{response.status_code}). The token in HARDWARIO_CLOUD_TOKEN may be '
                'expired, rotated or revoked, or issued for a different project. '
                'Get a current one at https://legacy.hardwario.cloud .')

        if 200 < response.status_code >= 300:
            text = response.text.strip('"')
            raise FirmwareApiException(f'{response.status_code}: {text}')

    def _post_upload(self, url, data, files):
        '''POST the payload with retries off.

        Firmware upload is not idempotent and the body is tens of megabytes;
        urllib3 replaying it costs minutes and buries the first failure under
        "Max retries exceeded".
        '''
        full_url = self._url + url
        logger.debug('POST {}', full_url)

        with requests.Session() as session:
            adapter = HTTPAdapter(max_retries=0)
            session.mount('http://', adapter)
            session.mount('https://', adapter)
            try:
                self._response = session.post(
                    full_url, headers=self._headers, data=data, files=files)
            except requests.exceptions.RequestException as e:
                # The underlying error is SSLEOFError / ConnectionReset /
                # BrokenPipe depending on timing, and says nothing useful to a
                # user. Keep it for --log-level debug and the log file; show the
                # actionable text. `from e` preserves it for anyone catching it.
                logger.debug('Upload transport error: {!r}', e)
                raise FirmwareApiException(
                    'Upload failed: the connection to the cloud service closed while '
                    'the firmware was being sent. This usually means the API token '
                    'stopped being accepted mid-upload (expired or rotated), or the '
                    'payload was rejected before it was fully read -- check the '
                    'firmware size and any proxy between you and the service. '
                    'Re-run with --log-level debug for the transport-level error.') from e

        if 200 < self._response.status_code >= 300:
            text = self._response.text.strip('"')
            raise FirmwareApiException(f'{self._response.status_code}: {text}')

        return self._response.json()

    def upload(self, name, version, app_path='.', zephyr_elf=False):
        '''Upload a firmware build.

        zephyr_elf is opt-in: the ELF carries debug symbols and source paths,
        so it is only sent when the caller asks for it.
        '''
        # Before opening any file or streaming anything.
        self.check_token()

        git_revision = None
        try:
            git_revision = subprocess.check_output(
                ['git', '-C', app_path, 'rev-parse', 'HEAD']).decode('ascii').strip()
        except Exception:
            pass

        data = {
            'name': name,
            'version': version,
            'git_revision': git_revision
        }

        files = {}

        hex_path = find_hex(app_path)
        logger.debug(f'hex_path={hex_path}')

        data['firmware_sha256'] = get_file_hash(hex_path)
        files['firmware_hex'] = open(hex_path, 'rb')

        app_update_path = test_file(app_path, 'build', 'zephyr', 'app_update.bin')
        if not app_update_path:
            ff = glob.glob(os.path.join(app_path, 'build', '*', 'zephyr', 'zephyr.signed.bin'))
            if ff:
                app_update_path = ff[0]
        logger.debug(f'app_update_path={app_update_path}')
        if app_update_path:
            data['app_update_sha256'] = get_file_hash(app_update_path)
            files['app_update_bin'] = open(app_update_path, 'rb')

        manifest_json_path = find_manifest_json(app_path, True)
        logger.debug(f'manifest_json_path={manifest_json_path}')
        if manifest_json_path:
            files['manifest'] = open(manifest_json_path, 'rb')

        if zephyr_elf:
            zephyr_elf_path = find_zephyr_elf(app_path, True)
            logger.debug(f'zephyr_elf_path={zephyr_elf_path}')
            if zephyr_elf_path:
                data['zephyr_elf_sha256'] = get_file_hash(zephyr_elf_path)
                files['zephyr_elf'] = open(zephyr_elf_path, 'rb')

        try:
            resp = self._post_upload('/v1/firmware', data, files)
        finally:
            for handle in files.values():
                handle.close()
        logger.debug(f'Response {resp}')
        return resp

    def list(self, offset: int = 0, limit=None):
        return self._list('/v1/firmware', {}, offset, limit)

    def detail(self, id):
        return self.request('GET', f'/v1/firmware/{id}')

    def delete(self, id):
        return self.request('DELETE', f'/v1/firmware/{id}')

    def _list(self, url, params: dict, offset=0, limit=None):
        cnt = 0
        params['offset'] = offset

        while True:
            params['limit'] = 100 if limit is None else limit

            for row in self.request('GET', url, params=params):
                cnt += 1
                yield row

            if limit is not None and limit >= cnt:
                break

            x_total = int(self._response.headers['x-total'])
            params['offset'] = offset + cnt

            if params['offset'] >= x_total:
                break
