from typing import Callable, Any
import paho.mqtt.client
import json
from loguru import logger


class MqttClient:
    def __init__(self, host, port, client_id=None, clean_session=None, username=None, password=None, cafile=None, certfile=None, keyfile=None):
        port = int(port)

        self.mqttc = paho.mqtt.client.Client(
            paho.mqtt.client.CallbackAPIVersion.VERSION2,
            client_id=client_id,
            clean_session=clean_session
        )
        self.mqttc.on_connect = self._mqtt_on_connect
        self.mqttc.on_message = self._mqtt_on_message
        self.mqttc.on_disconnect = self._mqtt_on_disconnect

        self._on_message = None
        self._on_connection = None
        self._subscriptions = []  # format: (topic, qos)

        if username:
            self.mqttc.username_pw_set(username, password)

        if cafile:
            self.mqttc.tls_set(cafile, certfile, keyfile)

        logger.info('MQTT broker host: {}, port: {}, use tls: {}', host, port, bool(cafile))

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

    @property
    def on_connection(self):
        return self._on_connection

    @on_connection.setter
    def on_connection(self, on_connection: Callable[[bool, str], None]):
        """Called as (connected, reason) whenever the broker link changes."""
        self._on_connection = on_connection

    def _report_connection(self, connected, reason=''):
        if self._on_connection:
            try:
                self._on_connection(connected, reason)
            except Exception as e:
                logger.error(f'on_connection handler failed: {e}')

    def _mqtt_on_connect(self, client, userdata, connect_flags, reason_code, properties):
        # paho's v2 reason code carries its own description, so there is no
        # table of CONNACK constants to keep in step here.
        if reason_code.is_failure:
            reason = reason_code.getName()
            logger.error('MQTT connection refused: {}', reason)
            self._report_connection(False, reason)
            return

        logger.info('Connected to MQTT broker')
        self._report_connection(True)

        for topic, qos in self._subscriptions:
            self.mqttc.subscribe(topic, qos=qos)
            logger.info(f"Subscribed to topic: {topic} with QoS {qos}")

    def _mqtt_on_disconnect(self, client, userdata, disconnect_flags, reason_code, properties):
        reason = reason_code.getName() if reason_code is not None else ''
        logger.info(f'Disconnected from MQTT broker: {reason}')
        self._report_connection(False, reason)

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
