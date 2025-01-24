from typing import Callable, Any
import paho.mqtt.client
from paho.mqtt.client import topic_matches_sub
import json
from loguru import logger


class MqttClient:
    def __init__(self, host, port, client_id=None, clean_session=None, username=None, password=None, cafile=None, certfile=None, keyfile=None):
        port = int(port)

        self.mqttc = paho.mqtt.client.Client(
            client_id=client_id,
            clean_session=clean_session
        )
        self.mqttc.on_connect = self._mqtt_on_connect
        self.mqttc.on_message = self._mqtt_on_message
        self.mqttc.on_disconnect = self._mqtt_on_disconnect

        self._on_message = None
        self._subscriptions = []  # format: (topic, qos)

        if username:
            self.mqttc.username_pw_set(username, password)

        if cafile:
            self.mqttc.tls_set(cafile, certfile, keyfile)

        logger.info('MQTT broker host: %s, port: %d, use tls: %s', host, port, bool(cafile))

        try:
            self.mqttc.connect(host, port, keepalive=10)
        except ConnectionRefusedError:
            raise ConnectionRefusedError(f'MQTT: Connection refused host: {host}, port: {port}, use tls: {bool(cafile)}')

        self._response_condition = 0
        self._response_topic = None
        self._response = None

        self._loop_start = False

    def loop_start(self):
        if self._loop_start:
            return

        self._loop_start = True
        self.mqttc.loop_start()

    def loop_forever(self):
        self.mqttc.loop_forever()

    @property
    def on_message(self):
        return self._on_message

    @on_message.setter
    def on_message(self, on_message: Callable[[str, Any], None]):
        self._on_message = on_message

    def _mqtt_on_connect(self, client, userdata, flags, rc):
        logger.info(f'Connected to MQTT broker with code {rc}')

        lut = {paho.mqtt.client.CONNACK_REFUSED_PROTOCOL_VERSION: 'incorrect protocol version',
               paho.mqtt.client.CONNACK_REFUSED_IDENTIFIER_REJECTED: 'invalid client identifier',
               paho.mqtt.client.CONNACK_REFUSED_SERVER_UNAVAILABLE: 'server unavailable',
               paho.mqtt.client.CONNACK_REFUSED_BAD_USERNAME_PASSWORD: 'bad username or password',
               paho.mqtt.client.CONNACK_REFUSED_NOT_AUTHORIZED: 'not authorised'}

        if rc != paho.mqtt.client.CONNACK_ACCEPTED:
            reason = lut.get(rc, 'unknown code')
            logger.error('Connection refused from reason: {reason}', )
            return

        for topic, qos in self._subscriptions:
            self.mqttc.subscribe(topic, qos=qos)
            logger.info(f"Subscribed to topic: {topic} with QoS {qos}")

    def _mqtt_on_disconnect(self, client, userdata, rc):
        logger.info(f'Disconnected from MQTT broker with code {rc}')

    def _mqtt_on_message(self, client, userdata, message):
        logger.debug(f'topic: {message.topic} payload: {message.payload}')

        payload = message.payload.decode('utf-8')
        try:
            payload = json.loads(payload)
        except Exception as e:
            logger.error(e)
            raise

        if self._on_message:
            self._on_message(message.topic, payload)

    def publish(self, topic, payload=None, qos=1):
        """ Publish message to topic """
        if isinstance(topic, list):
            topic = '/'.join(topic)
        return self.mqttc.publish(topic, json.dumps(payload), qos=qos)

    def subscribe(self, topic, qos=1):
        """ Subscribe to topic """
        if isinstance(topic, list):
            topic = '/'.join(topic)
        if topic in [sub[0] for sub in self._subscriptions]:
            logger.warning(f"Already subscribed to topic: {topic}")
            return
        self._subscriptions.append((topic, qos))
        self.mqttc.subscribe(topic, qos=qos)
        logger.info(f"Subscribed to topic: {topic} with QoS {qos}")

    def unsubscribe(self, topic):
        """ Unsubscribe from topic """
        self._subscriptions = [sub for sub in self._subscriptions if sub[0] != topic]
        self.mqttc.unsubscribe(topic)
        logger.info(f"Unsubscribed from topic: {topic}")
