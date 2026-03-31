from .base import DeviceInterface
import qwiic_icm20948
import math

class ICM20948Interface(DeviceInterface):
    def __init__(self, address):
        super().__init__(address)
        self.device = qwiic_icm20948.QwiicIcm20948()
        if not self.device.connected:
            print("The Qwiic ICM20948 device isn't connected. Please check your connection.")
            return
        self.device.begin()

    def read(self):
        """Read orientation from sensor, convert to human-readable units, and compute heading and pitch."""
        self.device.getAgmt()  # Read all axis and temp from sensor
        
        # Scaling factors for default settings: ±2g, ±250 dps, ±4900 µT
        accel_scale = 16384.0  # LSB/g for ±2g
        gyro_scale = 131.0     # LSB/dps for ±250 dps
        mag_scale = 0.15       # µT/LSB for ±4900 µT
        
        # Scaled sensor values
        accel_x_g = self.device.axRaw / accel_scale
        accel_y_g = self.device.ayRaw / accel_scale
        accel_z_g = self.device.azRaw / accel_scale
        mag_x_uT = self.device.mxRaw * mag_scale
        mag_y_uT = self.device.myRaw * mag_scale
        mag_z_uT = self.device.mzRaw * mag_scale
        
        # Calculate pitch (in radians)
        pitch = math.atan2(accel_x_g, math.sqrt(accel_y_g**2 + accel_z_g**2))
        pitch_deg = round(pitch * 180 / math.pi, 2)  # Convert to degrees
        
        # Tilt compensation for magnetometer
        mag_x_comp = mag_x_uT * math.cos(pitch) + mag_z_uT * math.sin(pitch)
        mag_y_comp = mag_y_uT
        
        # Calculate heading (in radians)
        heading = math.atan2(mag_y_comp, mag_x_comp)
        heading_deg = heading * 180 / math.pi
        if heading_deg < 0:
            heading_deg += 360
        heading_deg = round(heading_deg, 2)  # Round to 2 decimal places
        
        # Cardinal direction (16 points)
        cardinal_directions = [
            'N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
            'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW'
        ]
        segment = round(heading_deg / 22.5) % 16
        cardinal_direction = cardinal_directions[segment]
        
        return {
            'accel_x_g': round(accel_x_g, 2),
            'accel_y_g': round(accel_y_g, 2),
            'accel_z_g': round(accel_z_g, 2),
            'gyro_x_dps': round(self.device.gxRaw / gyro_scale, 2),
            'gyro_y_dps': round(self.device.gyRaw / gyro_scale, 2),
            'gyro_z_dps': round(self.device.gzRaw / gyro_scale, 2),
            'mag_x_uT': round(mag_x_uT, 2),
            'mag_y_uT': round(mag_y_uT, 2),
            'mag_z_uT': round(mag_z_uT, 2),
            'heading_deg': heading_deg,
            'pitch_deg': pitch_deg,
            'cardinal_direction': cardinal_direction
        }
