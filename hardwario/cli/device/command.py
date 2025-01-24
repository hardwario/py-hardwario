import os
import pylink
import click
from loguru import logger
from hardwario.cli.console import Console
from hardwario.cli.console.connector import FileLogConnector
from hardwario.cli.chester.validate import validate_hex_file
from hardwario.device.connector.jlink import PyLinkRTTConnector
from hardwario.chester.utils import find_hex


def nrf_flash(cli: click.Group):
    @cli.command('flash')
    @click.option('--halt', is_flag=True, help='Halt program.')
    @click.argument('hex_file', metavar='HEX_FILE_OR_ID', callback=validate_hex_file, default=find_hex('.', no_exception=True))
    @click.pass_context
    def command_flash(ctx, halt, hex_file):
        '''Flash application firmware (preserves UICR area).'''
        click.echo(f'File: {hex_file}')

        def progress(text, ctx={'len': 0}):
            if ctx['len']:
                click.echo('\r' + (' ' * ctx['len']) + '\r', nl=False)
            if not text:
                return
            ctx['len'] = len(text)
            click.echo(text, nl=text == 'Successfully completed')

        with ctx.obj['prog'] as prog:
            prog.program(hex_file, halt, progress=progress)

    return command_flash


def nrf_erase(cli: click.Group):
    @cli.command('erase')
    @click.option('--all', is_flag=True, help='Erase application firmware incl. UICR area.')
    @click.pass_context
    def command_erase(ctx, all):
        '''Erase application firmware w/o UICR area.'''
        with ctx.obj['prog'] as prog:
            if all:
                prog.erase_all()
            else:
                prog.erase_flash()
        click.echo('Successfully completed')

    return command_erase


def nrf_reset(cli: click.Group):
    @cli.command('reset')
    @click.option('--halt', is_flag=True, help='Halt program.')
    @click.pass_context
    def command_reset(ctx, halt):
        '''Reset application firmware.'''
        with ctx.obj['prog'] as prog:
            prog.reset()
            if halt:
                prog.halt()
        click.echo('Successfully completed')

    return command_reset


def nrf_console(cli: click.Group, family):

    default_history_file = os.path.expanduser(f"~/.hio_{family.lower()}_history")
    default_console_file = os.path.expanduser(f"~/.hio_{family.lower()}_console")

    @cli.command('console')
    @click.option('--reset', is_flag=True, help='Reset application firmware.')
    @click.option('--latency', type=int, help='Latency for RTT readout in ms.', show_default=True, default=50)
    @click.option('--history-file', type=click.Path(writable=True), show_default=True, default=default_history_file)
    @click.option('--console-file', type=click.Path(writable=True), show_default=True, default=default_console_file)
    @click.pass_context
    def command_console(ctx, reset, latency, history_file, console_file):
        '''Start interactive console for shell and logging.'''

        with ctx.obj['prog'] as prog:
            if reset:
                prog.reset()
                prog.go()

            device_info = prog.read_device_info()
            logger.info(f'device info: {device_info}')

            device_version = str(device_info[0])

            end = device_version.rfind('_')
            chip_name = device_version[len('DeviceVersion.'):end]

        prog = ctx.obj['prog']

        jlink = pylink.JLink()
        jlink.open(serial_no=prog.get_serial_number())
        jlink.set_speed(prog.get_speed())
        jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
        jlink.connect(chip_name)

        connector = PyLinkRTTConnector(jlink, latency=latency)

        if console_file:
            connector = FileLogConnector(connector, console_file)

        logger.remove(2)  # Remove stderr logger

        console = Console(connector, history_file=history_file)
        console.run()

    return command_console


def nrf_modem_flash(cli: click.Group):
    @cli.command('modem-flash')
    @click.argument('file', metavar='ZIP_FILE', type=click.Path(readable=True))
    @click.pass_context
    def command_modem_flash(ctx, file):
        '''Flash SiP modem firmware.'''
        # https://www.nordicsemi.com/Products/Development-hardware/nRF9160-DK/Download
        if not file.endswith('.zip'):
            raise click.ClickException('File must be a ZIP archive')

        with ctx.obj['prog'] as prog:
            click.echo(f'Flash: {file}')
            prog.program(file)
        click.echo('Successfully completed')

    return command_modem_flash
