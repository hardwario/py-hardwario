import click
import tempfile
import zipfile
import os
import socket
import time
import sys
from loguru import logger
import pylink
from hardwario.chester.nrfjprog import NRFJProg, DEFAULT_JLINK_SPEED_KHZ
from hardwario.device import jlink_setup


@click.group(name='lte')
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='Specify J-Link serial number.')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='Specify J-Link clock speed in kHz.', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.option('--nrfjprog-log', is_flag=True, help='Enable nrfjprog logging.')
@click.pass_context
def cli(ctx, jlink_sn, jlink_speed, nrfjprog_log):
    '''LTE Modem SoC commands.'''
    ctx.obj['prog'] = NRFJProg(
        'lte', log=nrfjprog_log, jlink_sn=jlink_sn, jlink_speed=jlink_speed)


@cli.command('flash')
@click.argument('file', metavar='FILE', type=click.Path(exists=True))
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='Specify J-Link serial number.')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='Specify J-Link clock speed in kHz.', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.pass_context
def command_flash(ctx, jlink_sn, jlink_speed, file):
    '''Flash modem firmware.'''

    if jlink_sn:
        ctx.obj['prog'].set_serial_number(jlink_sn)

    if jlink_speed != DEFAULT_JLINK_SPEED_KHZ:
        ctx.obj['prog'].set_speed(jlink_speed)

    def progress(text, ctx={'len': 0}):
        if ctx['len']:
            click.echo('\r' + (' ' * ctx['len']) + '\r', nl=False)
        if not text:
            return
        text = f'  {text}'
        ctx['len'] = len(text)
        click.echo(text, nl=text == 'Successfully completed')

    if file.endswith('.zip'):
        zf = zipfile.ZipFile(file)
        namelist = zf.namelist()
        if len(namelist) == 2:
            if 'modem.zip' not in namelist or 'application.hex' not in namelist:
                raise Exception('Invalid file.')

            with tempfile.TemporaryDirectory() as temp_dir:
                zf.extractall(temp_dir)
                with ctx.obj['prog'] as prog:
                    click.echo(f'Flash: modem.zip')
                    prog.program(os.path.join(
                        temp_dir, 'modem.zip'), progress=progress)
                    progress(None)
                    click.echo(f'Flash: application.hex')
                    prog.program(os.path.join(
                        temp_dir, 'application.hex'), progress=progress)
    else:
        with ctx.obj['prog'] as prog:
            click.echo(f'Flash: {file}')
            prog.program(file, progress=progress)

    progress(None)
    click.echo('Successfully completed')


@cli.command('erase')
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='Specify J-Link serial number.')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='Specify J-Link clock speed in kHz.', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.pass_context
def command_erase(ctx, jlink_sn, jlink_speed):
    '''Erase modem firmware.'''
    if jlink_sn:
        ctx.obj['prog'].set_serial_number(jlink_sn)

    if jlink_speed != DEFAULT_JLINK_SPEED_KHZ:
        ctx.obj['prog'].set_speed(jlink_speed)

    with ctx.obj['prog'] as prog:
        prog.erase_all()
    click.echo('Successfully completed')


@cli.command('reset')
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='Specify J-Link serial number.')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='Specify J-Link clock speed in kHz.', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.pass_context
def command_reset(ctx, jlink_sn, jlink_speed):
    '''Reset modem firmware.'''
    if jlink_sn:
        ctx.obj['prog'].set_serial_number(jlink_sn)

    if jlink_speed != DEFAULT_JLINK_SPEED_KHZ:
        ctx.obj['prog'].set_speed(jlink_speed)

    with ctx.obj['prog'] as prog:
        prog.reset()
    click.echo('Successfully completed')


@cli.command('trace')
@click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='Specify J-Link serial number.')
@click.option('--jlink-speed', type=int, metavar="SPEED", help='Specify J-Link clock speed in kHz.', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
@click.option('--file', '-f', 'filename', metavar='FILE', type=click.Path(writable=True))
@click.option('--tcp', 'tcpconnect', metavar='TCP', type=str, help='TCP connect to server, format: <host>:<port>')
@click.option('--duration', '-d', 'duration', metavar='DURATION', type=int, help='Duration in seconds, after which the trace will be stopped.')
@click.pass_context
def command_trace(ctx, jlink_sn, jlink_speed, filename, tcpconnect, duration):
    '''Modem trace.'''

    # sudo socat -d -d pty,link=/dev/virtual_serial_port,raw,echo=0,group-late=dialout,perm=0777 TCP-LISTEN:5555,reuseaddr,fork

    if jlink_sn:
        ctx.obj['prog'].set_serial_number(jlink_sn)

    if jlink_speed != DEFAULT_JLINK_SPEED_KHZ:
        ctx.obj['prog'].set_speed(jlink_speed)

    prog = ctx.obj['prog']

    with prog as p:
        pass

    jlink = jlink_setup('NRF9160_xxAA', serial_no=prog.get_serial_number(), speed=prog.get_speed())

    fd = None
    client_socket = None

    if filename:
        fd = open(filename, 'wb')

    if tcpconnect:
        host, port = tcpconnect.split(':')
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((host, int(port)))

    running = False

    while True:
        print('Starting modem trace...')

        text_len = 0
        last_text = ''
        num_up = 0
        buffer_index = 0
        num_bytes = 1000

        try:
            logger.info('Opening RTT')
            jlink.rtt_start()
            running = True

            for _ in range(100):
                try:
                    num_up = jlink.rtt_get_num_up_buffers()
                    num_down = jlink.rtt_get_num_down_buffers()
                    logger.info(f'RTT started, {num_up} up bufs, {num_down} down bufs.')
                    break
                except pylink.errors.JLinkRTTException:
                    time.sleep(0.1)
            else:
                raise Exception('Failed to find RTT block')

            for i in range(num_up):
                desc = jlink.rtt_get_buf_descriptor(i, 1)
                logger.info(f'Up buffer {i}: {desc}, "{desc.acName}"')
                if desc.acName == b'modem_trace':
                    buffer_index = i
                    num_bytes = min(desc.SizeOfBuffer, 1000)
                    break
            else:
                raise Exception('Not found modem trace channel in RTT.')

            logger.info(f'Modem trace buffer index: {buffer_index}')

            print('Started modem trace')
            start_time = time.time()
            recv_len = 0
            text_len = 0

            e_cnt = 0
            while True:
                try:
                    data = jlink.rtt_read(buffer_index, num_bytes)
                except Exception as e:
                    e_cnt += 1
                    if e_cnt > 10:
                        raise
                    continue

                if fd:
                    fd.write(data)
                    fd.flush()

                if client_socket:
                    try:
                        client_socket.send(data)
                    except Exception as e:
                        if text_len:
                            print()
                            text_len = 0
                        print(e)

                if text_len:
                    print(f"\r{' ' * text_len}\r", end='')
                if data:
                    recv_len += len(data)

                running = (time.time() - start_time)
                last_text = f'Receive: {recv_len} B ({running:.1f}s)'
                text_len = len(last_text)
                print(last_text, end='')
                sys.stdout.flush()

                if duration and running >= duration:
                    jlink.rtt_stop()
                    print(f'\nStopping modem trace.')
                    sys.exit(0)

        except Exception as e:
            if running:
                jlink.rtt_stop()
            if last_text:
                print()
            print('Restart exception:', str(e))
            time.sleep(0.5)
