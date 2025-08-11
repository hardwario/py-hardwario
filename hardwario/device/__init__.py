from loguru import logger
import pylink


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
    logger.info(f'J-Link firmware_outdated: {jlink.firmware_outdated()}')
    logger.info(f'J-Link firmware_newer: {jlink.firmware_newer()}')

    logger.info(f'J-Link device: {device}')

    jlink.connect(device)

    return jlink
