from os.path import join, exists, isfile, getsize, expanduser


DEFAULT_CACHE_PATH = expanduser("~/.hardwario/chester/cache")


def test_file(*paths):
    file_path = join(*paths)
    if exists(file_path) and isfile(file_path) and getsize(file_path) > 0:
        return file_path


def find_hex(app_path, no_exception=False):
    for out_path in (join(app_path, 'build'), join(app_path, 'build', 'zephyr')):
        for name in ('merged.hex', 'zephyr.hex'):
            hex_path = test_file(out_path, name)
            if hex_path:
                return hex_path

    if no_exception:
        return None

    raise Exception('No firmware found.')
