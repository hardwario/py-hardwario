import re
from hardwario.common import pib


class PIBException(pib.PIBException):
    pass


class PIB(pib.PIB):

    def __init__(self, buf=None):
        super().__init__(version=2, buf=buf, nrf=True)
