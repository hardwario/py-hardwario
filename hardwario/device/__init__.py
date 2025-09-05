from loguru import logger
import pylink
import click


def jlink_setup(device, serial_no=None, speed=2000):

    jlink = pylink.JLink()
    jlink.open(serial_no=serial_no)
    jlink.set_speed(speed)
    jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)

    logger.info(f'J-Link dll version: {jlink.version}')
    logger.info(f'J-Link dll compile_date: {jlink.compile_date}')
    try:
        logger.info(f'J-Link dll path: {jlink._library._path}')
    except Exception as _:
        pass
    logger.info(f'J-Link serial_number: {jlink.serial_number}')
    logger.info(f'J-Link firmware_version: {jlink.firmware_version}')

    try:
        firmware_outdated = jlink.firmware_outdated()
        logger.info(f'J-Link firmware_outdated: {firmware_outdated}')
    except Exception as _:
        firmware_outdated = False
        logger.info('J-Link firmware_outdated: not supported')

    try:
        firmware_newer = jlink.firmware_newer()
        logger.info(f'J-Link firmware_newer: {firmware_newer}')
    except Exception as _:
        firmware_newer = False
        logger.info('J-Link firmware_newer: not supported')

    if firmware_outdated:
        if click.confirm('Newer firmware version available. Can you update?', default=False):
            jlink.update_firmware()
            logger.info('Firmware updated. Please restart the program.')
            exit(0)

    if firmware_newer:
        if click.confirm('Firmware version is newer than DLL supports. Synchonize firmware with DLL?', default=False):
            jlink.invalidate_firmware()
            jlink.update_firmware()
            logger.info('Firmware synchronized. Please restart the program.')
            exit(0)

    logger.info(f'J-Link device: {device}')

    jlink.connect(device)

    return jlink
