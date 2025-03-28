import os
import sys
import re
import time
import click
import pylink
import queue
from loguru import logger
from hardwario.chester.firmwareapi import FirmwareApi, DEFAULT_API_URL
from hardwario.chester.nrfjprog import NRFJProg, DEFAULT_JLINK_SPEED_KHZ
from hardwario.chester.pib import PIB
from hardwario.chester.utils import find_hex
from hardwario.chester.connector import PyLinkRTTConnector
from hardwario.chester.cli.validate import *
from rttt.connectors import FileLogConnector
from rttt.console import Console
from rttt.event import Event, EventType

default_history_file = os.path.expanduser("~/.chester_history")
default_console_file = os.path.expanduser("~/.chester_console")
default_coredump_file = os.path.expanduser("~/.chester_coredump.bin")


@click.group(name='app')
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='J-Link serial number')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='J-Link clock speed in kHz', default=2000, show_default=True)
@click.option('--nrfjprog-log', is_flag=True, help='Enable nrfjprog log.')
@click.pass_context
def cli(ctx, jlink_sn, jlink_speed, nrfjprog_log):
    '''Application SoC commands.'''
    ctx.obj['prog'] = NRFJProg('app', log=nrfjprog_log, jlink_sn=jlink_sn, jlink_speed=jlink_speed)


@cli.command('flash')
@click.option('--halt', is_flag=True, help='Halt program.')
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='J-Link serial number')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='J-Link clock speed in kHz', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.argument('hex_file', metavar='HEX_FILE_OR_ID', callback=validate_hex_file, default=find_hex('.', no_exception=True))
@click.pass_context
def command_flash(ctx, halt, jlink_sn, jlink_speed, hex_file):
    '''Flash application firmware (preserves UICR area).'''
    click.echo(f'File: {hex_file}')

    def progress(text, ctx={'len': 0}):
        if ctx['len']:
            click.echo('\r' + (' ' * ctx['len']) + '\r', nl=False)
        if not text:
            return
        ctx['len'] = len(text)
        click.echo(text, nl=text == 'Successfully completed')

    ctx.obj['prog'].set_serial_number(jlink_sn)
    ctx.obj['prog'].set_speed(jlink_speed)

    with ctx.obj['prog'] as prog:
        prog.program(hex_file, halt, progress=progress)


@cli.command('erase')
@click.option('--all', is_flag=True, help='Erase application firmware incl. UICR area.')
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='J-Link serial number')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='J-Link clock speed in kHz', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.pass_context
def command_erase(ctx, all, jlink_sn, jlink_speed):
    '''Erase application firmware w/o UICR area.'''
    ctx.obj['prog'].set_serial_number(jlink_sn)
    ctx.obj['prog'].set_speed(jlink_speed)
    with ctx.obj['prog'] as prog:
        if all:
            prog.erase_all()
        else:
            prog.erase_flash()
    click.echo('Successfully completed')


@cli.command('reset')
@click.option('--halt', is_flag=True, help='Halt program.')
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='J-Link serial number')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='J-Link clock speed in kHz', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.pass_context
def command_reset(ctx, halt, jlink_sn, jlink_speed):
    '''Reset application firmware.'''
    ctx.obj['prog'].set_serial_number(jlink_sn)
    ctx.obj['prog'].set_speed(jlink_speed)
    with ctx.obj['prog'] as prog:
        prog.reset()
        if halt:
            prog.halt()
    click.echo('Successfully completed')


@cli.command('console')
@click.option('--reset', is_flag=True, help='Reset application firmware.')
@click.option('--latency', type=int, help='Latency for RTT readout in ms.', show_default=True, default=50)
@click.option('--history-file', type=click.Path(writable=True), show_default=True, default=default_history_file)
@click.option('--console-file', type=click.Path(writable=True), show_default=True, default=default_console_file)
@click.option('--coredump-file', type=click.File('wb', 'utf-8', lazy=True), show_default=True, default=default_coredump_file)
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='J-Link serial number')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='J-Link clock speed in kHz', default=2000, show_default=True)
@click.pass_context
def command_console(ctx, reset, latency, history_file, console_file, coredump_file, jlink_sn, jlink_speed):
    '''Start interactive console for shell and logging.'''

    # if coredump_file:
    #     os.makedirs(os.path.dirname(coredump_file), exist_ok=True)

    ctx.obj['prog'].set_serial_number(jlink_sn)
    ctx.obj['prog'].set_speed(jlink_speed)
    with ctx.obj['prog'] as prog:
        if reset:
            prog.reset()
            prog.go()

    logger.remove(2)  # Remove stderr logger

    prog = ctx.obj['prog']

    jlink = pylink.JLink()
    jlink.open(serial_no=prog.get_serial_number())
    jlink.set_speed(prog.get_speed())
    jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
    jlink.connect('NRF52840_xxAA')

    connector = PyLinkRTTConnector(jlink, latency=latency)

    if console_file:
        text = f'Console: J-Link sn: {prog.get_serial_number()}' if prog.get_serial_number() else 'Console'
        connector = FileLogConnector(connector, console_file, text=text)

    console = Console(connector, history_file=history_file)
    console.run()

    click.echo('TIP: After J-Link connection, it is crucial to power cycle the target device; otherwise, the CPU debug mode results in a permanently increased power consumption.')


@cli.group(name='pib')
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='J-Link serial number')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='J-Link clock speed in kHz', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.pass_context
def group_pib(ctx, jlink_sn, jlink_speed):
    '''HARDWARIO Product Information Block.'''
    ctx.obj['pib'] = PIB()
    ctx.obj['prog'].set_serial_number(jlink_sn)
    ctx.obj['prog'].set_speed(jlink_speed)


@group_pib.command('read')
@click.option('--json', 'out_json', is_flag=True, help='Output in JSON format.')
@click.pass_context
def command_pib_read(ctx, out_json):
    '''Read HARDWARIO Product Information Block from UICR.'''

    with ctx.obj['prog'] as prog:
        buffer = prog.read_uicr()

    pib = PIB(buffer)

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
@click.option('--product-name', type=str, help='Product name (max 16 characters).', default='CHESTER-M', prompt=True, show_default=True, callback=validate_pib_param)
@click.option('--hw-variant', type=str, help='Hardware variant.', default='', prompt='Hardware variant', show_default=True, callback=validate_pib_hw_variant)
@click.option('--hw-revision', type=str, help='Hardware revision in Rx.y format.', default='R3.2', prompt='Hardware revision', show_default=True, callback=validate_pib_param)
@click.option('--serial-number', type=str, help='Serial number in decimal format.', prompt=True, callback=validate_pib_param)
@click.option('--claim-token', type=str, help='Claim token for device self-registration (32 hexadecimal characters).', default='', prompt=True, show_default=True, callback=validate_pib_param)
@click.option('--ble-passkey', type=str, help='Bluetooth security passkey (max 16 characters).', default='123456', prompt=True, show_default=True, callback=validate_pib_param)
@click.option('--halt', is_flag=True, help='Halt program.')
@click.pass_context
def command_pib_write(ctx, vendor_name, product_name, hw_variant, hw_revision, serial_number, claim_token, ble_passkey, halt):
    '''Write HARDWARIO Product Information Block to UICR.'''
    logger.debug('command_pib_write: %s', (serial_number,
                 vendor_name, product_name, hw_revision, hw_variant, claim_token, ble_passkey))

    pib = ctx.obj['pib']
    buffer = pib.get_buffer()

    logger.debug('write uicr: %s', buffer.hex())

    with ctx.obj['prog'] as prog:
        prog.write_uicr(buffer, halt=halt)

    click.echo('Successfully completed')


@cli.group(name='uicr')
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='J-Link serial number')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='J-Link clock speed in kHz', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.pass_context
def group_uicr(ctx, jlink_sn, jlink_speed):
    '''UICR flash area.'''
    ctx.obj['prog'].set_serial_number(jlink_sn)
    ctx.obj['prog'].set_speed(jlink_speed)


@group_uicr.command('read')
@click.option('--format', type=click.Choice(['hex', 'bin']), help='Specify input format.', required=True)
@click.argument('file', type=click.File('wb'))
@click.pass_context
def command_uicr_read(ctx, format, file):
    '''Read generic UICR flash area to <FILE> or stdout.'''

    with ctx.obj['prog'] as prog:
        buffer = prog.read_uicr()

    if format == 'hex':
        file.write(buffer.hex().encode())

    elif format == 'bin':
        file.write(buffer)


@group_uicr.command('write')
@click.option('--format', type=click.Choice(['hex', 'bin']), help='Specify input format.', required=True)
@click.option('--halt', is_flag=True, help='Halt program.')
@click.argument('file', type=click.File('rb'))
@click.pass_context
def command_uicr_write(ctx, format, halt, file):
    '''Write generic UICR flash area from <FILE> or stdout.'''

    buffer = file.read()

    if buffer and format == 'hex':
        buffer = bytes.fromhex((''.join(buffer.decode())).strip())

    if buffer is None:
        raise click.BadParameter('Problem load buffer.')

    if len(buffer) > 128:
        raise click.BadParameter('Buffer has wrong size allowed is max 128B')

    logger.debug('write uicr: %s', buffer.hex())

    with ctx.obj['prog'] as prog:
        prog.write_uicr(buffer, halt=halt)


@cli.group(name='fw')
@click.option('--url', metavar='URL', required=True, default=os.environ.get('HARDWARIO_FW_API_URL', DEFAULT_API_URL), show_default=True)
@click.option('--token', metavar='TOKEN', help='User API token from https://legacy.hardwario.cloud .', required='--help' not in sys.argv, envvar='HARDWARIO_CLOUD_TOKEN')
@click.pass_context
def cli_fw(ctx, url, token):
    '''Firmware commands.'''
    ctx.obj['fwapi'] = FirmwareApi(url=url, token=token)


def validate_version(ctx, param, value):
    if re.match(r'^v\d{1,3}\.\d{1,3}\.\d{1,3}(-.*?)?$', value):
        return value
    raise click.BadParameter('Bad version format expect is example: v1.0.0-alpha .')


@cli_fw.command('upload')
@click.option('--name', type=str, help='Firmware name (max 100 characters).', prompt=True, required=True)
@click.option('--version', type=str, help='Firmware version (max 50 characters).', callback=validate_version, prompt=True, required=True)
@click.pass_context
def command_fw_upload(ctx, name, version):
    '''Upload application firmware.'''
    fw = ctx.obj['fwapi'].upload(name, version, '.')
    url = ctx.obj['fwapi'].url
    click.echo(f'Unique identifier: {fw["id"]}')
    click.echo(f'Sharable link    : {url[:-4]}/{fw["id"]}')


@cli_fw.command('list')
@click.option('--limit', type=click.IntRange(0, 100, clamp=True))
@click.pass_context
def command_fw_list(ctx, limit):
    '''List application firmwares.'''
    click.echo(f'{"UUID":32} {"Upload UTC date/time":20} Label')
    for fw in ctx.obj['fwapi'].list(limit=limit):
        dt = fw['created_at'][:10] + ' ' + fw['created_at'][11:-5]
        click.echo(f'{fw["id"]} {dt}  {fw["name"]}:{fw["version"]}')


@cli_fw.command('delete')
@click.option('--id', metavar="ID", required=True)
@click.confirmation_option(prompt='Are you sure you want to delete firmware ?')
@click.pass_context
def command_fw_delete(ctx, id):
    '''Delete firmware.'''
    fw = ctx.obj['fwapi'].delete(id)
    click.echo('OK')


@cli_fw.command('info')
@click.option('--id', metavar="ID", show_default=True, required=True)
@click.option('--show-all', is_flag=True, help='Show all properties.')
@click.pass_context
def command_fw_info(ctx, id, show_all):
    '''Info firmware detail.'''
    fw = ctx.obj['fwapi'].detail(id)
    url = ctx.obj['fwapi'].url
    click.echo(f'Unique identifier: {fw["id"]}')
    click.echo(f'Name:              {fw["name"]}')
    click.echo(f'Version:           {fw["version"]}')
    click.echo(f'Sharable link:     {url}/{fw["id"]}')
    click.echo(f'Upload date/time:  {fw["created_at"]}')
    click.echo(f'Commit revision:   {fw["git_revision"]}')
    click.echo(f'SHA256 firmware:   {fw["firmware_sha256"]}')
    click.echo(f'SHA256 app_update: {fw["app_update_sha256"]}')
    click.echo(f'SHA256 zephyr_elf: {fw["zephyr_elf_sha256"]}')
    if show_all:
        click.echo(f'Build Manifest:    {json.dumps(fw["manifest"])}')


@cli.command('command')
@click.option('--reset', is_flag=True, help='Reset application firmware.')
@click.option('--timeout', '-t', type=float, metavar='TIMEOUT', help='Read line timeout in seconds.', default=1, show_default=True)
@click.option('--console-file', type=click.Path(writable=True), show_default=True, default=default_console_file)
@click.argument('command', type=str)
@click.pass_context
def command_pokus(ctx, reset, timeout, console_file, command):
    '''Send command to the device and print response.'''

    prog = ctx.obj['prog']

    jlink = pylink.JLink()
    jlink.open(serial_no=prog.get_serial_number())
    jlink.set_speed(prog.get_speed())
    jlink.set_tif(pylink.enums.JLinkInterfaces.SWD)
    jlink.connect('NRF52840_xxAA')

    if reset:
        jlink.reset(halt=False)
        time.sleep(1)

    connector = PyLinkRTTConnector(jlink, latency=50)

    if console_file:
        connector = FileLogConnector(connector, console_file, text="Command")

    q = queue.Queue()

    def handle_event(event: Event):
        if event.type == EventType.OUT:
            q.put(event.data)

    connector.on(handle_event)

    connector.open()

    for line in command.splitlines():
        connector.handle(Event(EventType.IN, line))

    deadline = time.time() + timeout

    while True:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        try:
            resp = q.get(timeout=remaining)
            print(resp)
        except queue.Empty:
            break

    connector.close()
