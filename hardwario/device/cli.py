import os
import pylink
import click
import string
import json
import time
from loguru import logger
from rttt.connectors import PyLinkRTTConnector, FileLogConnector
from rttt.console import Console
from hardwario.common.utils import download_url
from hardwario.common.pib import PIB, PIBException
from hardwario.chester.utils import find_hex
from hardwario.device.nrfjprog import NRFJProg, DEFAULT_JLINK_SPEED_KHZ
from hardwario.resources import get_resource_path


def validate_hex_file(ctx, param, value):
    # print('validate_hex_file', ctx.obj, param.name, value)
    if len(value) == 32 and all(c in string.hexdigits for c in value):
        return download_url(f'https://firmware.hardwario.com/chester/{value}/hex', filename=f'{value}.hex')

    if os.path.exists(value):
        return value

    raise click.BadParameter(f'Path \'{value}\' does not exist.')


def make_command_flash(cli: click.Group):
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


def make_command_erase(cli: click.Group):
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


def make_command_reset(cli: click.Group):
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


def make_command_console(cli: click.Group, family):

    default_history_file = os.path.expanduser(f"~/.hio_history")
    default_console_file = os.path.expanduser(f"~/.hio_console")

    @cli.command('console')
    @click.option('--reset', is_flag=True, help='Reset application firmware.')
    @click.option('--latency', type=int, help='Latency for RTT readout in ms.', show_default=True, default=50)
    @click.option('--history-file', type=click.Path(writable=True), show_default=True, default=default_history_file)
    @click.option('--console-file', type=click.Path(writable=True), show_default=True, default=default_console_file)
    @click.option('--device', type=str, help='J-Link device name.', default=None)
    @click.pass_context
    def command_console(ctx, reset, latency, history_file, console_file, device):
        '''Start interactive console for shell and logging.'''

        with ctx.obj['prog'] as prog:
            if reset:
                prog.reset()
                prog.go()

            if not device:
                device = prog.get_chip_name()

        prog = ctx.obj['prog']

        jlink = pylink.JLink()
        jlink.open(serial_no=prog.get_serial_number())
        jlink.set_speed(prog.get_speed())
        jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
        jlink.connect(device)

        connector = PyLinkRTTConnector(jlink, latency=latency)

        if console_file:
            connector = FileLogConnector(connector, console_file)

        logger.remove(2)  # Remove stderr logger

        console = Console(connector, history_file=history_file)
        console.run()

    return command_console


def make_command_modem_flash(cli: click.Group):
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


def validate_pib_param(ctx, param, value):
    # print('validate_pib_param', ctx.obj, param.name, value)
    try:
        getattr(ctx.obj['pib'], f'set_{param.name}')(value)
    except PIBException as e:
        raise click.BadParameter(str(e))
    return value


def make_group_pib(cli: click.Group, family):

    @cli.group(name='pib')
    @click.pass_context
    def group_pib(ctx):
        '''HARDWARIO Product Information Block.'''
        ctx.obj['pib'] = PIB(2, nrf=True)

    @group_pib.command('read')
    @click.option('--json', 'out_json', is_flag=True, help='Output in JSON format.')
    @click.pass_context
    def command_pib_read(ctx, out_json):
        '''Read HARDWARIO Product Information Block from UICR.'''

        buffer = None
        with ctx.obj['prog'] as prog:
            buffer = prog.read_uicr_pib()

        logger.info(f'buffer: {buffer.hex()}')

        pib = PIB(2, buffer, nrf=True)

        if out_json:
            click.echo(json.dumps(pib.get_dict(), indent=2))
        else:
            click.echo(f'Vendor name: {pib.get_vendor_name()}')
            click.echo(f'Product name: {pib.get_product_name()}')
            click.echo(f'Hardware variant: {pib.get_hw_variant()}')
            click.echo(f'Hardware revision: {pib.get_hw_revision()}')
            click.echo(f'Serial number: {pib.get_serial_number()}')
            click.echo(f'Claim token: {pib.get_claim_token()}')
            click.echo(f'BLE passkey: {pib.get_ble_passkey()}')

    @group_pib.command('write')
    @click.option('--vendor-name', type=str, help='Vendor name (max 16 characters).', default='HARDWARIO', prompt=True, show_default=True, callback=validate_pib_param)
    @click.option('--product-name', type=str, help='Product name (max 16 characters).', default=family.upper(), prompt=True, show_default=True, callback=validate_pib_param)
    @click.option('--hw-variant', type=str, help='Hardware variant.', default='', prompt='Hardware variant', show_default=True, callback=validate_pib_param)
    @click.option('--hw-revision', type=str, help='Hardware revision in Rx.y format.', default='R0.1', prompt='Hardware revision', show_default=True, callback=validate_pib_param)
    @click.option('--serial-number', type=str, help='Serial number in decimal format.', prompt=True, callback=validate_pib_param)
    @click.option('--claim-token', type=str, help='Claim token for device self-registration (32 hexadecimal characters).', default='', prompt=True, show_default=True, callback=validate_pib_param)
    @click.option('--ble-passkey', type=str, help='Bluetooth security passkey (max 16 characters).', default='123456', prompt=True, show_default=True, callback=validate_pib_param)
    @click.option('--halt', is_flag=True, help='Halt program.')
    @click.pass_context
    def command_pib_write(ctx, vendor_name, product_name, hw_variant, hw_revision, serial_number, claim_token, ble_passkey, halt):
        '''Write HARDWARIO Product Information Block to UICR.'''

        logger.info(f'write pib: {vendor_name}, {product_name}, {hw_variant}, {hw_revision}, {serial_number}, {claim_token}, {ble_passkey}')

        pib = ctx.obj['pib']

        if claim_token == '':
            pib.gen_claim_token()

        buffer = pib.get_buffer()

        logger.info(f'buffer: {buffer.hex()}')

        with ctx.obj['prog'] as prog:
            if family == 'nRF91':
                click.echo('Recovering device (This operation might take 30s.)')
                prog.recover()
                click.echo('Writing image to disable ap protect.')
                prog.program_file(get_resource_path('nrf91_disable_ap_protect.hex'))

            click.echo('Writing Product Information Block')
            prog.write_uicr_pib(buffer, halt=halt)

        click.echo('Successfully completed')


@click.group(name='device', help='Commands for devices.')
@click.pass_context
def cli(ctx):
    pass


def make_group(family: str):
    @cli.group(name=family.lower(), help=f'Commands for {family} devices.')
    @click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='J-Link serial number')
    @click.option('--jlink-speed', type=int, metavar="SPEED", help='J-Link clock speed in kHz', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
    @click.pass_context
    def group(ctx, jlink_sn, jlink_speed):
        ctx.obj['prog'] = NRFJProg(family, jlink_sn=jlink_sn, jlink_speed=jlink_speed)
        ctx.obj['family'] = family

    make_command_flash(group)
    make_command_erase(group)
    make_command_reset(group)
    make_command_console(group, family)

    if family in ['nRF91']:
        make_group_pib(group, family)
        make_command_modem_flash(group)

    return group


for family in ['nRF51', 'nRF52', 'nRF53', 'nRF54H', 'nRF54L', 'nRF91']:
    make_group(family)
