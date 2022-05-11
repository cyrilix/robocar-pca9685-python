"""
Compute steering from camera images

Usage:
rc-pca9685 [steering|throttle] [-u USERNAME | --mqtt-username=USERNAME] [--mqtt-password=PASSWORD] \
        [--mqtt-broker=HOSTNAME] [--mqtt-topic=TOPIC] [--mqtt-client-id=CLIENT_ID] [--i2c-bus=BUS] \
        [--i2c-address=ADDRESS] [--pca9685-channel=CHANNEL] [--left-pulse=LEFT_PULSE] [--right-pulse=RIGHT_PULSE] \
        [--max-pulse=MAX_PULSE] [--min-pulse=MIN_PULSE] [--zero-pulse=ZEO_PULSE]

Options:
-h --help                                                Show this screen.
-u USERID      --mqtt-username=USERNAME                  MQTT user
-p PASSWORD    --mqtt-password=PASSWORD                  MQTT password
-b HOSTNAME    --mqtt-broker=HOSTNAME                    MQTT broker host
-C CLIENT_ID   --mqtt-client-id=CLIENT_ID                MQTT client id
-t TOPIC       --mqtt-topic-camera=TOPIC                 MQTT topic where to read camera frames
-b BUS         --i2c-bus=BUS                             I2C bus number
-a ADDRESS     --i2c-address=ADDRESS                     I2C base address
-c CHANNEL     --pca9685-channel=CHANNEL                 Device channel
-l LEFT_PULSE  --left-pulse=LEFT_PULSE                   Pulse for left steering
-r RIGHT_PULSE --right-pulse=RIGHT_PULSE                 Pulse for right steering
-M MAX_PULSE   --max-pulse=MAX_PULSE                     Max Pulse for throttle
-m MIN_PULSE   --min-pulse=MIN_PULSE                     Min Pulse for throttle
-z ZERO_PULE   --zero-pulse=ZEO_PULSE                    Zero Pulse for throttle
"""
import logging
import os

from docopt import docopt
import paho.mqtt.client as mqtt

from donkeycar.parts import actuator
import donkeycar

from events.events_pb2 import SteeringMessage
from events.events_pb2 import ThrottleMessage

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

default_client_id = "robocar-pca9685-python"


def init_mqtt_steering_client(steering_controller: actuator.PWMSteering, broker_host: str, user: str, password: str, client_id: str,
                     steering_topic: str) -> mqtt.Client:
    logger.info("Start steering part")
    client = mqtt.Client(client_id=client_id, clean_session=True, userdata=None, protocol=mqtt.MQTTv311)

    def on_connect(client, userdata, flags, rc):
        logger.info("Register callback on topic %s", steering_topic)
        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe(steering_topic)

    def on_steering_message(mqtt_client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
        try:
            steering_msg = SteeringMessage()
            steering_msg.ParseFromString(msg.payload)
            steering_controller.run_threaded(steering_msg.Steering)
        except:
            logger.debug("unexpected error: unable to process steering, skip message")

    client.username_pw_set(user, password)
    client.on_connect = on_connect
    client.on_message = on_steering_message
    logger.info("Connect to mqtt broker")
    client.connect(host=broker_host, port=1883, keepalive=60)
    logger.info("Connected to mqtt broker")
    return client


def init_mqtt_throttle_client(throttle_controller: actuator.PWMThrottle, broker_host: str, user: str, password: str,
                              client_id: str, throttle_topic: str) -> mqtt.Client:
    logger.info("Start throttle part")
    client = mqtt.Client(client_id=client_id, clean_session=True, userdata=None, protocol=mqtt.MQTTv311)

    def on_connect(client, userdata, flags, rc):
        logger.info("Register callback on topic %s", throttle_topic)
        # Subscribing in on_connect() means that if we lose the connection and
        # reconnect then subscriptions will be renewed.
        client.subscribe(throttle_topic)

    def on_throttle_message(mqtt_client: mqtt.Client, userdata, msg: mqtt.MQTTMessage):
        try:
            throttle_msg = ThrottleMessage()
            throttle_msg.ParseFromString(msg.payload)
            throttle_controller.run_threaded(throttle_msg.Throttle)
        except:
            logger.debug("unexpected error: unable to process throttle, skip message")

    client.username_pw_set(user, password)
    client.on_connect = on_connect
    client.on_message = on_throttle_message
    logger.info("Connect to mqtt broker")
    client.connect(host=broker_host, port=1883, keepalive=60)
    logger.info("Connected to mqtt broker")
    return client


def execute_from_command_line():
    logging.basicConfig(level=logging.INFO)

    args = docopt(__doc__)

    broker_host = get_default_value(args["--mqtt-broker"], "MQTT_BROKER", "localhost")
    user = get_default_value(args["--mqtt-username"], "MQTT_USERNAME", "")
    password = get_default_value(args["--mqtt-password"], "MQTT_PASSWORD", "")
    client_id = get_default_value(args["--mqtt-client-id"], "MQTT_CLIENT_ID", default_client_id)
    topic = get_default_value(args["--mqtt-topic"], "MQTT_TOPIC", "/pca9685")
    i2c_bus = get_default_value(args["--i2c-bus"], "I2C_BUS", 0)
    i2c_address = get_default_value(args["--i2c-address"], "I2C_ADDRESS", 40)
    pca9685_channel = get_default_value(args["--i2c-address"], "PCA9685_CHANNEL", 0)

    pin_id = "PCA9685.{bus}:{address}.{channel}".format(bus=i2c_bus, address=i2c_address,channel=pca9685_channel)

    if args["steering"]:
        steering_pin = donkeycar.parts.pins.pwm_pin_by_id(pin_id)
        steering = actuator.PWMSteering(steering_pin, left_pulse=args["--left-pulse"], right_pulse=args["--right-pulse"])
        client = init_mqtt_steering_client(steering_controller=steering, broker_host=broker_host, user=user,
                                           password=password, client_id=client_id, steering_topic=topic)
    elif args["throttle"]:
        throttle_pin = donkeycar.parts.pins.pwm_pin_by_id("PCA9685.0:40.7")
        throttle = actuator.PWMThrottle(throttle_pin, max_pulse=args["--max-pulse"], min_pulse=args["--min-pulse"],
                                        zero_pulse=args["--zero-pulse"])
        client = init_mqtt_throttle_client(throttle_controller=throttle, broker_host=broker_host, user=user,
                                           password=password, client_id=client_id, throttle_topic=topic)
    else:
        raise Exception('invalid mode selected, must be steering or throttle')

    client.loop_forever()


def get_default_value(value, env_var: str, default_value) -> str:
    if value:
        return value
    if env_var in os.environ:
        return os.environ[env_var]
    return default_value
