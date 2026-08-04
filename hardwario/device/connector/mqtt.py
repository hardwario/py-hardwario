from loguru import logger
from rttt.connectors import Connector, Middleware
from rttt.event import Event, EventType, conn_event
from hardwario.common.mqtt_client import MqttClient

CONN_SOURCE = 'mqtt'


class MqttBridgeMiddleware(Middleware):
    """Mirror a connector's terminal and logger output onto MQTT.

    Terminal input is not passed straight to the wrapped connector; it is
    published to the input topic and only reaches the connector once it comes
    back from the broker, so remote observers see the same input the local
    console sent.
    """

    def __init__(self, connector: Connector, mqtt: MqttClient, topic='hardwario/console') -> None:
        super().__init__(connector)
        self.mqtt = mqtt
        self.topic = topic

    def open(self):
        self.mqtt.subscribe([self.topic, 'input'])
        self.mqtt.on_message = self._on_message
        self.mqtt.on_connection = self._on_connection
        self.mqtt.loop_start()
        super().open()

    def _on_connection(self, connected, reason=''):
        # Reported under its own source: this middleware can sit on top of an
        # RTT connector, and a broker outage must not read as the device
        # having gone away.
        self._emit(conn_event(CONN_SOURCE, 'connected' if connected else 'disconnected', reason))

    def handle(self, event: Event):
        if event.type == EventType.IN:
            self.mqtt.publish([self.topic, 'input'], event.data)
        else:
            super().handle(event)

    def _on_message(self, topic, payload):
        if topic.split('/')[-1] == 'input':
            self.connector.handle(Event(EventType.IN, payload))

    def _on(self, event: Event):
        if event.type == EventType.LOG:
            self.mqtt.publish([self.topic, 'logger'], event.data)
        elif event.type == EventType.OUT:
            self.mqtt.publish([self.topic, 'terminal'], event.data)
        super()._on(event)


class MqttClientConnector(Connector):
    """Consume a console published on MQTT by MqttBridgeMiddleware."""

    def __init__(self, mqtt: MqttClient, topic='hardwario/console') -> None:
        super().__init__()
        self.mqtt = mqtt
        self.topic = topic

    def open(self):
        for suffix in ('terminal', 'logger', 'input'):
            self.mqtt.subscribe([self.topic, suffix])
        self.mqtt.on_message = self._on_message
        self.mqtt.on_connection = self._on_connection
        self.mqtt.loop_start()
        self._emit(Event(EventType.OPEN, ''))

    def _on_connection(self, connected, reason=''):
        self._emit(conn_event(CONN_SOURCE, 'connected' if connected else 'disconnected', reason))

    def close(self):
        self._emit(Event(EventType.CLOSE, ''))

    def handle(self, event: Event):
        if event.type == EventType.IN:
            self.mqtt.publish([self.topic, 'input'], event.data)

    def _on_message(self, topic, payload):
        suffix = topic.split('/')[-1]
        if suffix == 'terminal':
            self._emit(Event(EventType.OUT, payload))
        elif suffix == 'logger':
            self._emit(Event(EventType.LOG, payload))
        elif suffix == 'input':
            self._emit(Event(EventType.IN, payload))
        else:
            logger.debug(f'Ignoring MQTT topic: {topic}')
