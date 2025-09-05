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

    if firmware_outdated or firmware_newer:
        text_ask = 'A newer J-Link firmware version is available. Would you like to update?'
        text_done = 'J-Link firmware has been updated. Please run the program again.'
        if firmware_newer:
            text_ask = 'The J-Link firmware version is newer than the DLL supports. Would you like to synchronize with the DLL?'
            text_done = 'J-Link firmware has been synchronized with the DLL. Please run the program again.'

        if click.confirm(text_ask, default=False):
            if firmware_newer:
                jlink.invalidate_firmware()
            jlink.update_firmware()
            logger.info(text_done)
            click.echo(text_done)
            exit(0)

    logger.info(f'J-Link device: {device}')

    jlink.connect(device)

    return jlink
