from .base import DeviceInterface
from SDL_Pi_INA3221 import INA3221

class INA3221Interface(DeviceInterface):
    def __init__(self, address):
        super().__init__(address)
        self.device = INA3221(address=address)

    def read(self):
        """Read voltage from channel 1."""
        voltage = self.device.getBusVoltage_V(1)
        return {'voltage': voltage}