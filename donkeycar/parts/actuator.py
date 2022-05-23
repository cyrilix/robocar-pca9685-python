"""
actuators.py
Classes to control the motors and servos. These classes
are wrapped in a mixer class before being used in the drive loop.
"""

import logging
import time

import donkeycar as dk
from donkeycar.parts.pins import PwmPin, PinState

logger = logging.getLogger(__name__)


#
# pwm/duty-cycle/pulse
# - Standard RC servo pulses range from 1 millisecond (full reverse)
#   to 2 milliseconds (full forward) with 1.5 milliseconds being neutral (stopped).
# - These pulses are typically send at 50 hertz (every 20 milliseconds).
# - This means that, using the standard 50hz frequency, a 1 ms pulse
#   represents a 5% duty cycle and a 2 ms pulse represents a 10% duty cycle.
# - The important part is the length of the pulse;
#   it must be in the range of 1 ms to 2ms.
# - So this means that if a different frequency is used, then the duty cycle
#   must be adjusted in order to get the 1ms to 2ms pulse.
# - For instance, if a 60hz frequency is used, then a 1 ms pulse requires
#   a duty cycle of 0.05 * 60 / 50 = 0.06 (6%) duty cycle
# - We default the frequency of our PCA9685 to 60 hz, so pulses in
#   config are generally based on 60hz frequency and 12 bit values.
#   We use 12 bit values because the PCA9685 has 12 bit resolution.
#   So a 1 ms pulse is 0.06 * 4096 ~= 246, a neutral pulse of 0.09 duty cycle
#   is 0.09 * 4096 ~= 367 and full forward pulse of 0.12 duty cycles
#   is 0.12 * 4096 ~= 492
# - These are generalizations that are useful for understanding the underlying
#   api call arguments.  The final choice of duty-cycle/pulse length depends
#   on your hardware and perhaps your strategy (you may not want to go too fast,
#   and so you may choose is low max throttle pwm)
#

def duty_cycle(pulse_ms: float, frequency_hz: float) -> float:
    """
    Calculate the duty cycle, 0 to 1, of a pulse given
    the frequency and the pulse length

    :param pulse_ms:float the desired pulse length in milliseconds
    :param frequency_hz:float the pwm frequency in hertz
    :return:float duty cycle in range 0 to 1
    """
    ms_per_cycle = 1000 / frequency_hz
    duty = pulse_ms / ms_per_cycle
    return duty


def pulse_ms(pulse_bits: int) -> float:
    """
    Calculate pulse width in milliseconds given a
    12bit pulse (as a PCA9685 would use).
    Donkeycar throttle and steering PWM values are
    based on PCA9685 12bit pulse values, where
    0 is zero duty cycle and 4095 is 100% duty cycle.

    :param pulse_bits:int 12bit integer in range 0 to 4095
    :return:float pulse length in milliseconds
    """
    if pulse_bits < 0 or pulse_bits > 4095:
        raise ValueError("pulse_bits must be in range 0 to 4095 (12bit integer)")
    return pulse_bits / 4095


class PulseController:
    """
    Controller that provides a servo PWM pulse using the given PwmPin
    See pins.py for pin provider implementations.
    """

    def __init__(self, pwm_pin: PwmPin, pwm_scale: float = 1.0, pwm_inverted: bool = False) -> None:
        """
        :param pwm_pin:PwnPin pin that will emit the pulse.
        :param pwm_scale:float scaling the 12 bit pulse value to compensate
                        for non-standard pwm frequencies.
        :param pwm_inverted:bool True to invert the duty cycle
        """
        self.pwm_pin = pwm_pin
        self.scale = pwm_scale
        self.inverted = pwm_inverted
        self.started = pwm_pin.state() != PinState.NOT_STARTED

    def set_pulse(self, pulse: int) -> None:
        """
        Set the length of the pulse using a 12 bit integer (0..4095)
        :param pulse:int 12bit integer (0..4095)
        """
        if pulse < 0 or pulse > 4095:
            raise ValueError("pulse must be in range 0 to 4095")

        if not self.started:
            self.pwm_pin.start()
            self.started = True
        if self.inverted:
            pulse = 4095 - pulse
        self.pwm_pin.duty_cycle(int(pulse * self.scale) / 4095)

    def run(self, pulse: int) -> None:
        """
        Set the length of the pulse using a 12 bit integer (0..4095)
        :param pulse:int 12bit integer (0..4095)
        """
        self.set_pulse(pulse)


class PWMSteering:
    """
    Wrapper over a PWM pulse controller to convert angles to PWM pulses.
    """
    LEFT_ANGLE = -1
    RIGHT_ANGLE = 1

    def __init__(self, controller, left_pulse, right_pulse):

        if controller is None:
            raise ValueError("PWMSteering requires a set_pulse controller to be passed")
        set_pulse = getattr(controller, "set_pulse", None)
        if set_pulse is None or not callable(set_pulse):
            raise ValueError("controller must have a set_pulse method")

        self.controller = controller
        self.left_pulse = left_pulse
        self.right_pulse = right_pulse
        self.pulse = dk.utils.map_range(0, self.LEFT_ANGLE, self.RIGHT_ANGLE,
                                        self.left_pulse, self.right_pulse)
        self.running = True
        logger.info('PWM Steering created')

    def update(self):
        while self.running:
            self.controller.set_pulse(self.pulse)

    def run_threaded(self, angle):
        # map absolute angle to angle that vehicle can implement.
        self.pulse = dk.utils.map_range(angle,
                                        self.LEFT_ANGLE, self.RIGHT_ANGLE,
                                        self.left_pulse, self.right_pulse)
        logger.debug(f"new steering value {angle} -> {self.pulse}")

    def run(self, angle):
        self.run_threaded(angle)
        self.controller.set_pulse(self.pulse)

    def shutdown(self):
        # set steering straight
        self.pulse = 0
        time.sleep(0.3)
        self.running = False


class PWMThrottle:
    """
    Wrapper over a PWM pulse controller to convert -1 to 1 throttle
    values to PWM pulses.
    """
    MIN_THROTTLE = -1
    MAX_THROTTLE = 1

    def __init__(self, controller, max_pulse, min_pulse, zero_pulse):

        if controller is None:
            raise ValueError("PWMThrottle requires a set_pulse controller to be passed")
        set_pulse = getattr(controller, "set_pulse", None)
        if set_pulse is None or not callable(set_pulse):
            raise ValueError("controller must have a set_pulse method")

        self.controller = controller
        self.max_pulse = max_pulse
        self.min_pulse = min_pulse
        self.zero_pulse = zero_pulse
        self.pulse = zero_pulse

        # send zero pulse to calibrate ESC
        logger.info("Init ESC")
        self.controller.set_pulse(self.max_pulse)
        time.sleep(0.01)
        self.controller.set_pulse(self.min_pulse)
        time.sleep(0.01)
        self.controller.set_pulse(self.zero_pulse)
        time.sleep(1)
        self.running = True
        logger.info('PWM Throttle created')

    def update(self):
        while self.running:
            self.controller.set_pulse(self.pulse)

    def run_threaded(self, throttle):
        if throttle > 0:
            self.pulse = dk.utils.map_range(throttle, 0, self.MAX_THROTTLE,
                                            self.zero_pulse, self.max_pulse)
        else:
            self.pulse = dk.utils.map_range(throttle, self.MIN_THROTTLE, 0,
                                            self.min_pulse, self.zero_pulse)
        logger.debug(f"new steering value {throttle} -> {self.pulse}")

    def run(self, throttle):
        self.run_threaded(throttle)
        self.controller.set_pulse(self.pulse)

    def shutdown(self):
        # stop vehicle
        self.run(0)
        self.running = False


class MockController(object):
    def __init__(self):
        pass

    def run(self, pulse):
        pass

    def shutdown(self):
        pass
