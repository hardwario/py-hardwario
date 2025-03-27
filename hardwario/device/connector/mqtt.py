from typing import Callable
from loguru import logger
from hardwario.common.mqtt_client import MqttClient
from hardwario.cli.console.connector import EventType, Connector


class MqttBridgeConnector(Connector):

    def __init__(self, connector: Connector, mqtt: MqttClient, topic='hardwario/console') -> None:
        self.mqtt = mqtt
        self.topic = topic
        self.connector = connector

    def open(self, emit_event: Callable[[EventType, str], None]):
        self.emit_event = emit_event
        self.mqtt.subscribe([self.topic, 'input'])
        self.mqtt.on_message = self._on_message
        self.mqtt.loop_start()
        self.connector.open(self._emit_event)

    def close(self):
        self.connector.close()

    def input(self, line: str):
        self.mqtt.publish([self.topic, 'input'], line)

    def _on_message(self, topic, payload):
        t = topic.split('/')
        if t[-1] == 'input':
            self.connector.input(payload)

    def _emit_event(self, type: EventType, data):
        if type == EventType.LOGGER_OUT:
            self.mqtt.publish([self.topic, 'logger'], data)
        elif type == EventType.TERMINAL_OUT:
            self.mqtt.publish([self.topic, 'terminal'], data)
        self.emit_event(type, data)


class MqttClientConnector(Connector):

    def __init__(self, mqtt: MqttClient, topic='hardwario/console') -> None:
        self.mqtt = mqtt
        self.topic = topic

    def open(self, emit_event: Callable[[EventType, str], None]):
        self.emit_event = emit_event
        self.mqtt.subscribe([self.topic, 'terminal'])
        self.mqtt.subscribe([self.topic, 'logger'])
        self.mqtt.subscribe([self.topic, 'input'])
        self.mqtt.on_message = self._on_message
        self.mqtt.loop_start()

    def close(self):
        pass

    def input(self, line: str):
        self.mqtt.publish([self.topic, 'input'], line)

    def _on_message(self, topic, payload):
        t = topic.split('/')
        if t[-1] == 'terminal':
            self.emit_event(EventType.TERMINAL_OUT, payload)
        elif t[-1] == 'logger':
            self.emit_event(EventType.LOGGER_OUT, payload)
        elif t[-1] == 'input':
            self.emit_event(EventType.TERMINAL_IN, payload)
