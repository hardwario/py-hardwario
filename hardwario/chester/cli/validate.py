

import json
import os
import string
import click
from hardwario.chester.pib import PIBException
from hardwario.common.utils import download_url


DEFAULT_CACHE_PATH = os.path.expanduser("~/.hardwario/chester/cache")


def validate_hex_file(ctx, param, value):
    # print('validate_hex_file', ctx.obj, param.name, value)
    if len(value) == 32 and all(c in string.hexdigits for c in value):
        return download_url(f'https://firmware.hardwario.com/chester/{value}/hex', filename=f'{value}.hex', cache_path=DEFAULT_CACHE_PATH)

    if os.path.exists(value):
        return value

    raise click.BadParameter(f'Path \'{value}\' does not exist.')


def validate_pib_param(ctx, param, value):
    # print('validate_pib_param', ctx.obj, param.name, value)
    try:
        getattr(ctx.obj['pib'], f'set_{param.name}')(value)
    except PIBException as e:
        raise click.BadParameter(str(e))
    return value


def validate_pib_hw_variant(ctx, param, value):
    filepath = download_url(f'https://production.hardwario.com/api/v1/product/family/chester', filename=f'chester_product_list.json', cache_path=DEFAULT_CACHE_PATH)
    products = json.load(open(filepath))

    product_name = ctx.obj['pib'].get_product_name()
    product = None
    for product in products:
        if product['name'] == product_name:
            break
    else:
        raise click.BadParameter('Bad Product name not from list.')

    if not product['assembly_variants']:
        raise click.BadParameter('Bad Product assembly_variants not from list.')

    if value not in product['assembly_variants']:
        raise click.BadParameter('Bad Hardware variant not from list.')

    ctx.obj['pib'].set_hw_variant(value)

    return value
