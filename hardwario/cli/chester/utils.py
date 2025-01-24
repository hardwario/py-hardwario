import os
from os.path import join, expanduser
import hashlib
import click
import time
import requests


DEFAULT_CACHE_PATH = expanduser("~/.hardwario/chester/cache")


def download_url(url, filename=None, cache_path=DEFAULT_CACHE_PATH):

    if not filename:
        if url.startswith("https://firmware.hardwario.com/chester"):
            filename = url[39:].replace('/', '.')
        else:
            filename = hashlib.sha256(url.encode()).hexdigest()

    if cache_path:
        os.makedirs(cache_path, exist_ok=True)
        filename = join(cache_path, filename)
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


def rtt_read_line(prog, channel, timeout, cache={'Terminal': '', 'Logger': ''}):
    timeout = time.time() + timeout
    while time.time() < timeout:
        i = cache[channel].find('\n')
        if i > -1:
            line = cache[channel][:i]
            cache[channel] = cache[channel][i + 1:]
            return line

        data = prog.rtt_read(channel)
        if data:
            cache[channel] += data

        i = cache[channel].find('\n')
        if i < 0:
            continue

        line = cache[channel][:i]
        cache[channel] = cache[channel][i + 1:]
        return line


def bytes_to_human(size):
    # for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
    #     if size < 1024.0:
    #         break
    #     size /= 1024.0
    if size < 1024.0:
        unit = 'B'
    else:
        unit = 'KB'
        size /= 1024.0

    return f"{size:.1f} {unit}"


def join_path(*args):
    return '/'.join(args).replace('//', '/')
