import time
from loguru import logger
from pynrfjprog import APIError
from pynrfjprog.Parameters import RTTChannelDirection
from hardwario.device.nrfjprog import (
    NRFJProg as NRFJProgBase,
    NRFJProgException,
    NRFJProgOpenException,
    NRFJProgDeviceFamilyException,
    NRFJProgRTTNoChannels,
    DEFAULT_JLINK_SPEED_KHZ
)


class NRFJProg(NRFJProgBase):

    def __init__(self, mcu, jlink_sn=None, jlink_speed=DEFAULT_JLINK_SPEED_KHZ, log=False, log_suffix=None):
        if mcu not in ('app', 'lte'):
            raise NRFJProgException(f'Unknown MCU type: {mcu}')

        super().__init__(mcu, jlink_sn, jlink_speed, log, log_suffix)

    def write_uicr(self, buffer: bytes, halt=False):
        if self.device_family != 'app':
            raise NRFJProgException('Invalid MCU support only for app')

        self.reset()
        self.halt()

        self.erase_uicr()
        self.write(self.get_uicr_address() + 0x80, buffer, True)

        self.reset()
        if halt:
            self.halt()
        else:
            self.go()

    def read_uicr(self):
        if self.device_family != 'app':
            raise NRFJProgException('Invalid MCU support only for app')
        return bytes(self.read(self.get_uicr_address() + 0x80, 128))

    def rtt_start(self):  # type: ignore
        if self._rtt_channels is not None:
            return self._rtt_channels

        logger.debug('RTT Start')
        super().rtt_start()

        self.rtt_set_control_block_address(0x20002650)

        for _ in range(100):
            is_found, address = self.rtt_get_control_block_info()
            if is_found:
                logger.debug('RTT control block found at 0x{:08X}', address)
                break
            time.sleep(0.1)
        else:
            raise NRFJProgException('Failed to find RTT block')

        channel_count = self.rtt_read_channel_count()
        logger.debug(f'RTT channel count {channel_count}')

        channels = {}
        for index in range(channel_count[0]):
            name, size = self.rtt_read_channel_info(index, RTTChannelDirection.DOWN_DIRECTION)
            if size < 1:
                continue
            channels[name] = {
                'down': {
                    'index': index,
                    'size': size
                }
            }
        for index in range(channel_count[1]):
            name, size = self.rtt_read_channel_info(index, RTTChannelDirection.UP_DIRECTION)
            if size < 1:
                continue
            if name not in channels:
                channels[name] = {}
            channels[name]['up'] = {
                'index': index,
                'size': size
            }

        self._rtt_channels = channels
        return self._rtt_channels

    def rtt_stop(self):
        if self._rtt_channels is None:
            return
        # super().rtt_async_flush()
        # super().rtt_stop() #  WHY: if call rtt_stop then Can not found RTT start block after rtt_start, needs reset for work
        self._rtt_channels = None
        logger.debug('RTT Stopeed')

    def rtt_is_running(self):
        return self._rtt_channels is not None

    def rtt_write(self, channel, msg, encoding='utf-8'):  # type: ignore
        if self._rtt_channels is None:
            raise NRFJProgRTTNoChannels('Can not write, try call rtt_start first')
        if isinstance(channel, str):
            channel = self._rtt_channels[channel]['down']['index']
        logger.debug('channel: {} msg: {}', channel, repr(msg))
        return super().rtt_write(channel, msg, encoding)

    def rtt_read(self, channel, length=None, encoding='utf-8'):  # type: ignore
        if self._rtt_channels is None:
            raise NRFJProgRTTNoChannels('Can not read, try call rtt_start first')
        if isinstance(channel, str):
            ch = self._rtt_channels[channel]['up']
            if length is None:
                length = ch['size']
            channel = ch['index']

        try:
            msg = super().rtt_read(channel, length, encoding=None)  # type: ignore
            if msg:
                logger.debug('channel: {} msg: {}', channel, repr(msg))
            if encoding:
                msg = msg.decode(encoding, errors="backslashreplace")  # type: ignore
            return msg
        except APIError.APIError as e:
            logger.exception(e)
            if self.read_connected_emu_fwstr():
                raise NRFJProgException(
                    'J-Link communication error occurred (check the flat cable between J-Link and the device)')
            else:
                raise NRFJProgException(
                    'J-Link communication error occurred (check the USB cable between the computer and J-Link)')
