import os
import hashlib
import click
import requests

DEFAULT_CACHE_PATH = os.path.expanduser("~/.hardwario/cache")


def get_file_hash(filename, hash_name='sha256', buf_size=65535):
    hash = hashlib.new(hash_name)
    with open(filename, 'rb') as f:
        for data in iter(lambda: f.read(buf_size), b''):
            hash.update(data)
    return hash.hexdigest()


def download_url(url, filename=None, cache_path=DEFAULT_CACHE_PATH):

    if not filename:
        if url.startswith("https://firmware.hardwario.com/chester"):
            filename = url[39:].replace('/', '.')
        else:
            filename = hashlib.sha256(url.encode()).hexdigest()

    if cache_path:
        os.makedirs(cache_path, exist_ok=True)
        filename = os.path.join(cache_path, filename)
        if os.path.exists(filename):
            return filename

    response = requests.get(url, stream=True, allow_redirects=True)
    if response.status_code != 200:
        raise Exception(response.text)
    total_length = response.headers.get('content-length')
    with open(filename, "wb") as f:
        if total_length is None:  # no content length header
            f.write(response.content)
        else:
            with click.progressbar(length=int(total_length), label='Download ') as bar:
                dl = 0
                for data in response.iter_content(chunk_size=4096):
                    dl += len(data)
                    f.write(data)
                    bar.update(dl)
    return filename
