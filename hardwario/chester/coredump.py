import binascii
from loguru import logger


COREDUMP_PREFIX_STR = "#CD:"
COREDUMP_BEGIN_STR = COREDUMP_PREFIX_STR + "BEGIN#"
COREDUMP_END_STR = COREDUMP_PREFIX_STR + "END#"
COREDUMP_ERROR_STR = COREDUMP_PREFIX_STR + "ERROR CANNOT DUMP#"


class Coredump:
    def __init__(self):
        self.has_begin = False
        self.has_end = False
        self.has_error = False
        self.data = b''

    def feed_line(self, line: str):
        line = line.strip()
        if not line:
            return

        if line.find(COREDUMP_BEGIN_STR) >= 0:
            self.has_begin = True
            self.data = b''
            return

        elif line.find(COREDUMP_END_STR) >= 0:
            self.has_end = True
            return

        elif line.find(COREDUMP_ERROR_STR) >= 0:
            self.has_error = True
            return

        if not self.has_begin:
            return

        prefix_idx = line.find(COREDUMP_PREFIX_STR)
        if prefix_idx < 0:
            self.has_end = True
            self.has_error = True
            return

        if self.has_end:
            raise Exception("Coredump already finished")

        hex_str = line[prefix_idx + len(COREDUMP_PREFIX_STR):]

        try:
            self.data += binascii.unhexlify(hex_str)
        except Exception as e:
            logger.error("Cannot parse coredump hex_str: {}".format(hex_str))
            self.has_error = True
            self.has_end = True

    def reset(self):
        self.has_begin = False
        self.has_end = False
        self.has_error = False
        self.data = b''
