from loguru import logger
import pylink
import click
from rttt.connectors import MCPMiddleware, MCPPortInUseError
from rttt.utils import parse_listen

DEFAULT_MCP_LISTEN = '127.0.0.1:8090'

LOOPBACK_HOSTS = ('127.0.0.1', 'localhost', '::1')


def mcp_setup(connector, listen, name, token=None):
    '''Wrap connector in the rttt MCP server middleware and report its URL.'''
    try:
        connector = MCPMiddleware(connector, listen=listen, name=name, token=token)
    except MCPPortInUseError as e:
        raise click.ClickException(
            f'{e}. Close the other console, pick a different address with '
            '--mcp-listen HOST:PORT, or disable the server with --no-mcp.')

    host, port = parse_listen(listen)
    click.echo(f'MCP server: http://{host}:{port}/mcp')

    if not token and host not in LOOPBACK_HOSTS:
        click.echo(
            f'Warning: {host} is not a loopback address and no --mcp-token is set, so anyone '
            'who can reach this port can flash the device and read or write its memory.', err=True)

    return connector


def jlink_setup(device, serial_no=None, speed=2000):

    jlink = pylink.JLink()
    jlink.open(serial_no=serial_no)
    jlink.set_speed(speed)
    jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)

    logger.info(f'J-Link dll version: {jlink.version}')
    logger.info(f'J-Link dll compile_date: {jlink.compile_date}')
    try:
        logger.info(f'J-Link dll path: {jlink._library._path}')
    except Exception:
        pass
    logger.info(f'J-Link serial_number: {jlink.serial_number}')
    logger.info(f'J-Link firmware_version: {jlink.firmware_version}')

    try:
        firmware_outdated = jlink.firmware_outdated()
        logger.info(f'J-Link firmware_outdated: {firmware_outdated}')
    except Exception:
        firmware_outdated = False
        logger.info('J-Link firmware_outdated: not supported')

    try:
        firmware_newer = jlink.firmware_newer()
        logger.info(f'J-Link firmware_newer: {firmware_newer}')
    except Exception:
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
