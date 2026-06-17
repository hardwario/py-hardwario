from os.path import join, exists, isfile, getsize, expanduser
import os
import glob


DEFAULT_CACHE_PATH = expanduser("~/.hardwario/chester/cache")


def test_file(*paths):
    file_path = join(*paths)
    if exists(file_path) and isfile(file_path) and getsize(file_path) > 0:
        return file_path


def find_hex(app_path, no_exception=False):
    for out_path in (join(app_path, 'build'), join(app_path, 'build', 'zephyr')):
        for name in ('merged.hex', 'zephyr.hex', 'merged_chester_nrf52840.hex'):
            hex_path = test_file(out_path, name)
            if hex_path:
                return hex_path

    if no_exception:
        return None

    raise Exception('No firmware found.')


def find_manifest_json(app_path, no_exception=False):
    for out_path in (join(app_path, 'build'), join(app_path, 'build', 'zephyr')):
        manifest_path = test_file(out_path, 'dfu_application.zip_manifest.json')
        if manifest_path:
            return manifest_path

    if no_exception:
        return None

    raise Exception('No manifest found.')


def find_zephyr_elf(app_path, no_exception=False):
    zephyr_elf_path = test_file(app_path, 'build', 'zephyr', 'zephyr.elf')
    if zephyr_elf_path:
        return zephyr_elf_path

    ff = glob.glob(os.path.join(app_path, 'build', '*', 'zephyr', 'zephyr.elf'))
    if len(ff) > 2:
        raise Exception('Too many zephyr.elf found.')
    for f in ff:
        if 'mcuboot' in ff:
            continue
        return f

    if no_exception:
        return None

    raise Exception('No zephyr.elf found.')
