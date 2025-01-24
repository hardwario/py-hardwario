
from typing import Callable
import pylink
import time
import threading
from loguru import logger
from hardwario.cli.console.connector import EventType, Connector


class PyLinkRTTConnector(Connector):

    def __init__(self, jlink: pylink.JLink, block_address=None, latency=50) -> None:
        self.jlink = jlink
        self.block_address = block_address
        self.rtt_read_delay = latency / 1000.0
        self.is_running = False
        self.terminal_up_index = 0
        self.terminal_up_size = 0
        self.terminal_down_index = 0
        self.terminal_down_size = 0
        self.logger_up_index = None
        self.logger_up_size = 0

    def open(self, emit_event: Callable[[EventType, str], None]):
        self.emit_event = emit_event
        self._cache = {0: '', 1: ''}

        logger.info(f"Opening RTT{' control block found at 0x{:08X}'.format(self.block_address) if self.block_address else ''}")
        self.jlink.rtt_start(self.block_address)

        for _ in range(100):
            try:
                num_up = self.jlink.rtt_get_num_up_buffers()
                num_down = self.jlink.rtt_get_num_down_buffers()
                logger.info(f'RTT started, {num_up} up bufs, {num_down} down bufs.')
                break
            except pylink.errors.JLinkRTTException:
                time.sleep(0.1)
        else:
            raise Exception('Failed to find RTT block')

        if num_up == 0:
            raise Exception('No RTT down buffers found')

        self.is_running = True

        for i in range(num_up):
            desc = self.jlink.rtt_get_buf_descriptor(i, 1)
            logger.info(f'Up buffer {i}: {desc}')
            if desc.name == 'Terminal':
                self.terminal_up_index = i
                self.terminal_up_size = desc.SizeOfBuffer
            elif desc.name == 'Logger':
                self.logger_up_index = i
                self.logger_up_size = desc.SizeOfBuffer

        for i in range(num_down):
            desc = self.jlink.rtt_get_buf_descriptor(i, 0)
            logger.info(f'Down buffer {i}: {desc}')
            if desc.name == 'Terminal':
                self.terminal_down_index = i
                self.terminal_down_size = desc.SizeOfBuffer
                break

        self.old_mode = True
        if self.logger_up_index is None:
            self.old_mode = True
            logger.info('Using old RTT implementation')

        self.thread = threading.Thread(target=self._read_task, daemon=True)
        self.thread.start()
        logger.info('RTT opened')

    def close(self):
        logger.info('Closing RTT')
        if not self.is_running:
            return
        self.is_running = False
        self.thread.join()
        self.jlink.rtt_stop()
        logger.info('RTT closed')

    def input(self, line: str):
        data = bytearray(f'{line}\n', "utf-8")
        for i in range(0, len(data), self.terminal_down_size):
            chunk = data[i:i + self.terminal_down_size]
            self.jlink.rtt_write(self.terminal_down_index, list(chunk))

        self.emit_event(EventType.TERMINAL_IN, line)

    def _read_task(self):
        while self.is_running:
            channels = [
                (self.terminal_up_index, min(1000, self.terminal_up_size), EventType.TERMINAL_OUT),
                (self.logger_up_index, min(1000, self.logger_up_size), EventType.LOGGER_OUT)
            ]
            for idx, num_bytes, event_type in channels:
                if idx is None:
                    continue

                data = self.jlink.rtt_read(idx, num_bytes)
                if data:
                    lines = bytes(data).decode('utf-8', errors="backslashreplace")
                    if lines:
                        lines = self._cache[idx] + lines

                        while True:
                            end = lines.find('\n')
                            if end < 0:
                                self._cache[idx] = lines
                                break

                            line = lines[:end]
                            lines = lines[end + 1:]

                            if line.endswith('\r'):
                                line = line[:-1]

                            if self.old_mode and line.startswith('#'):
                                self.emit_event(EventType.LOGGER_OUT, line)
                            else:
                                self.emit_event(event_type, line)

            time.sleep(self.rtt_read_delay)
