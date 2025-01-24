from abc import ABCMeta, abstractmethod
from datetime import datetime
from typing import Callable, Tuple
import enum
import os
import time
import threading
from loguru import logger


@enum.unique
class EventType(enum.Enum):
    TERMINAL_OUT = 1  # terminal line out
    TERMINAL_IN = 2  # terminal line in
    LOGGER_OUT = 3  # logger line out


class Connector(metaclass=ABCMeta):

    @abstractmethod
    def open(self, emit_event: Callable[[EventType, str], None]):
        pass

    @abstractmethod
    def close(self):
        pass

    @abstractmethod
    def input(self, line: str):
        pass


class DebugConnector(Connector):
    def __init__(self, delay=0.5) -> None:
        self.i = 0
        self.delay = delay
        self.is_running = False

    def input(self, line: str):
        logger.info(f'input: {line}')

    def open(self, emit_event: Callable[[EventType, str], None]):
        logger.info('open')
        self.emit_event = emit_event
        self.is_running = True
        self.thread = threading.Thread(target=self._task, daemon=True)
        self.thread.start()

    def close(self):
        logger.info('close')
        if not self.is_running:
            return
        self.is_running = False
        self.thread.join()

    def _task(self):
        while self.is_running:
            self.i += 1
            if self.i % 2 == 0:
                self.emit_event(EventType.LOGGER_OUT, f'log {self.i}')
            else:
                self.emit_event(EventType.TERMINAL_OUT, f'term {self.i}')
            time.sleep(self.delay)


class FileLogConnector(Connector):
    def __init__(self, connector: Connector, file_path: str) -> None:
        self.connector = connector
        logger.info(f'file_path: {file_path}')
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        self.fd = open(file_path, 'a')

    def open(self, emit_event: Callable[[EventType, str], None]):
        self.emit_event = emit_event
        self.fd.write(f'{ "*" * 80 }\n')
        self.connector.open(self._emit_event)

    def close(self):
        self.connector.close()

    def input(self, line: str):
        self.connector.input(line)

    def _emit_event(self, type: EventType, data):
        if type == EventType.LOGGER_OUT:
            self._console_log(' # ', data)
        elif type == EventType.TERMINAL_OUT:
            self._console_log(' > ', data)
        elif type == EventType.TERMINAL_IN:
            self._console_log(' < ', data)
        self.emit_event(type, data)

    def _console_log(self, prefix, line):
        t = datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:23]
        self.fd.write(f'{t}{prefix}{line}\n')
        self.fd.flush()
