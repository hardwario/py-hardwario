import time
from loguru import logger
from pynrfjprog import APIError, LowLevel
from pynrfjprog.Parameters import EraseAction, MemoryType, ReadbackProtection

DEFAULT_JLINK_SPEED_KHZ = LowLevel.API._DEFAULT_JLINK_SPEED_KHZ


class NRFJProgException(Exception):
    pass


class NRFJProgOpenException(NRFJProgException):
    pass


class NRFJProgDeviceFamilyException(NRFJProgOpenException):
    pass


class NRFJProgRTTNoChannels(NRFJProgException):
    pass


class NRFJProg(LowLevel.API):

    def __init__(self, device_family=None, jlink_sn=None, jlink_speed=DEFAULT_JLINK_SPEED_KHZ, log=False, log_suffix=None):
        self.device_family = device_family
        self.log = log
        self.log_suffix = log_suffix
        self._rtt_channels = None
        self._jlink_ip = None
        self.set_serial_number(jlink_sn)
        self.set_speed(jlink_speed)
        self.is_opened = False

    def set_serial_number(self, serial_number):
        self._jlink_sn = int(serial_number) if serial_number is not None else None

    def set_speed(self, speed):
        self._jlink_speed = int(speed) if speed is not None else DEFAULT_JLINK_SPEED_KHZ

    def set_remote(self, host):
        if host is None:
            self._jlink_ip = None
            return
        if host.startswith('ip '):  # remove ip prefix from connection string
            host = host[3:]

        if host.startswith('tunnel:'):
            self._jlink_ip = (host, 0)
            return

        s = host.split(':')
        if len(s) == 1:
            self._jlink_ip = (host, 0)
        elif len(s) == 2:
            self._jlink_ip = (s[0], int(s[1]))
        else:
            raise NRFJProgException(f'Invalid J-Link remote host: {host}')

    def get_serial_number(self):
        return self._jlink_sn

    def get_speed(self):
        return self._jlink_speed

    def open(self):
        logger.debug('Opening')
        try:
            super().__init__(LowLevel.DeviceFamily.UNKNOWN, log=self.log)
            super().open()

            if self._jlink_ip:
                logger.debug('Connecting to J-Link at {}:{}', *self._jlink_ip)
                self.connect_to_emu_with_ip(self._jlink_ip[0], self._jlink_ip[1], jlink_speed_khz=self._jlink_speed)

            elif self._jlink_sn:
                self.connect_to_emu_with_snr(self._jlink_sn, jlink_speed_khz=self._jlink_speed)

            else:
                self.connect_to_emu_without_snr(jlink_speed_khz=self._jlink_speed)

        except APIError.APIError as e:
            if e.err_code == APIError.NrfjprogdllErr.NO_EMULATOR_CONNECTED:
                raise NRFJProgOpenException(
                    'No J-Link found (check USB cable)')
            if e.err_code == APIError.NrfjprogdllErr.LOW_VOLTAGE:
                raise NRFJProgOpenException(
                    'Detected low voltage on J-Link (check power supply and cable)')
            raise NRFJProgOpenException(str(e))

        device_family = self.read_device_family()

        if self.device_family:
            if self.device_family == 'app':
                if device_family != 'NRF52':
                    raise NRFJProgDeviceFamilyException(
                        f'An incorrect MCU was detected. The expected device family is {self.device_family}')
            elif self.device_family == 'lte':
                if device_family != 'NRF91':
                    raise NRFJProgDeviceFamilyException(
                        f'An incorrect MCU was detected. The expected device family is {self.device_family}')
            elif self.device_family.upper() != device_family:
                raise NRFJProgDeviceFamilyException(
                    f'An incorrect MCU was detected. The expected device family is {self.device_family.upper()} but {device_family} was detected')

        self.select_family(device_family)
        self.is_opened = True

        # print(self.read_device_info())
        logger.debug('Opened')

    def close(self):
        logger.debug('Closing')
        super().close()
        self.is_opened = False
        logger.debug('Closed')

    def reset(self):
        self.sys_reset()

    def erase_flash(self):
        self.disable_bprot()
        for des in self.read_memory_descriptors(False):
            if des.type == MemoryType.CODE:
                page_size = des.size // des.num_pages
                for addr in range(0, des.size, page_size):
                    self.erase_page(addr)

    def program(self, file_path, halt=False, progress=lambda x: None):
        self.reset()
        self.halt()

        progress('Erasing...')
        self.erase_file(file_path, chip_erase_mode=EraseAction.ERASE_SECTOR)

        progress('Flashing...')
        self.program_file(file_path)

        progress('Verifying...')
        self.verify_file(file_path)

        if halt:
            progress('Resetting (HALT)...')
            self.reset()
            self.halt()
        else:
            progress('Resetting (GO)...')
            self.reset()
            self.go()

        progress('Successfully completed')

    def get_uicr_address(self):
        for des in self.read_memory_descriptors(False):
            if des.type == MemoryType.UICR:
                return des.start
        raise NRFJProgException('UICR descriptor not found.')

    def get_chip_name(self):
        device_info = self.read_device_info()
        logger.debug(f'device info: {device_info}')

        name = device_info[0].name
        end = name.rfind('_')
        device = name[:end]

        if device == 'NRF9120_xxAA':
            return 'NRF9151_XXCA'

        return device

    def get_uicr_pib_address(self):
        device_family = self.read_device_family()
        if device_family == 'NRF52':
            return self.get_uicr_address() + 0x80
        if device_family == 'NRF91':
            # return 0x00FF8000 + 0x108
            return self.get_uicr_address() + 0x108

        raise NRFJProgException('Invalid MCU support only for NRF52 and NRF91')

    def read_uicr_pib(self):
        addr = self.get_uicr_pib_address()
        return bytes(self.read(addr, 128))

    def write_uicr_pib(self, buffer: bytes, halt=False):
        addr = self.get_uicr_pib_address()

        self.reset()
        self.halt()

        family = self.read_device_family()
        if family == 'NRF52':
            self.erase_uicr()

        self.write(addr, buffer, True)

        self.reset()
        if halt:
            self.halt()
        else:
            self.go()

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, type, value, traceback):
        self.close()
