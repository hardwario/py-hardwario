import os
import sys
import click
from loguru import logger
import hardwario

DEFAULT_LOG_LEVEL = 'DEBUG'
DEFAULT_LOG_FILE = os.path.expanduser("~/.hardwario/cli.log")

os.makedirs(os.path.expanduser("~/.hardwario"), exist_ok=True)


@click.group(name='hardwario')
@click.option('--log-level', type=click.Choice(['debug', 'info', 'success', 'warning', 'error', 'critical']),
              help='Log level to stderr', default="critical", show_default=True)
@click.version_option(hardwario.__version__, prog_name='hardwario')
def cli(log_level):
    '''HARDWARIO Command Line Tool.'''
    logger.add(sys.stderr, level=log_level.upper())


def main():
    '''Application entry point.'''

    logger.remove()
    logger.add(DEFAULT_LOG_FILE,
               format='{time} | {level} | {name}.{function}: {message}',
               level='TRACE',
               rotation='10 MB',
               retention=3)

    logger.debug('Argv: {}', sys.argv)
    logger.debug('Module: hardwario.common Version: {}', hardwario.__version__)

    try:
        with logger.catch(reraise=True, exclude=KeyboardInterrupt):
            cli(obj={})
    except KeyboardInterrupt:
        pass
    except Exception as e:
        click.secho(str(e), err=True, fg='red')
        if os.getenv('DEBUG', False):
            raise e
        sys.exit(1)
