import click
from hardwario.device.nrfjprog import NRFJProg, DEFAULT_JLINK_SPEED_KHZ
from hardwario.cli.device import command


@click.group(name='device', help='Commands for devices.')
@click.pass_context
def cli(ctx):
    pass


def create_group(family: str):
    @cli.group(name=family.lower(), help=f'Commands for {family} devices.')
    @click.option('--jlink-sn', '-n', type=int, metavar='SERIAL_NUMBER', help='JLink serial number')
    @click.option('--jlink-speed', type=int, metavar="SPEED", help='JLink clock speed in kHz', default=DEFAULT_JLINK_SPEED_KHZ, show_default=True)
    @click.pass_context
    def group(ctx, jlink_sn, jlink_speed):
        ctx.obj['prog'] = NRFJProg(family, jlink_sn=jlink_sn, jlink_speed=jlink_speed)

    command.nrf_flash(group)
    command.nrf_erase(group)
    command.nrf_reset(group)
    command.nrf_console(group, family)

    if family in ['nRF91']:
        command.nrf_modem_flash(group)

    return group


for family in ['nRF51', 'nRF52', 'nRF53', 'nRF54H', 'nRF54L', 'nRF91']:
    create_group(family)
