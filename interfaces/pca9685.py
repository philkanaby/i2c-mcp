from .base import DeviceInterface
from adafruit_servokit import ServoKit

class PCA9685Interface(DeviceInterface):
    def __init__(self, address):
        super().__init__(address)
        self.device = ServoKit(channels=16, address=address)
        for channel in range(16):
            self.device.servo[channel].set_pulse_width_range(500,2400)

    def write(self, value, channel):
        """Set the servo angle on the specified channel."""
        if channel is None:
            raise ValueError("Channel must be specified for PCA9685.")
        self.device.servo[channel].angle = value
