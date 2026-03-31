import json
import os
import importlib
import smbus
import logging
from typing import Dict, Any, List, Optional

from mcp.server.fastmcp import FastMCP

# ========================= CONFIG & CORE LOGIC =========================
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

CONFIG_FILE = 'i2c_config.json'

COMMON_I2C_DEVICES: Dict[str, List[str]] = {
    "0x40": ["PCA9685 16-channel PWM Servo Controller", "INA3221 Current/Power Monitor"],
    "0x41": ["INA3221 Current/Power Monitor", "PCA9685 (alt address)"],
    "0x44": ["PCA9685 16-channel PWM Servo Controller"],
    "0x68": ["ICM20948 / MPU6050 IMU", "Many gyro/accel sensors"],
    "0x69": ["SparkFun 9DoF ICM-20948 Orientation Sensor"],
    # Add more as you discover them — or extend with web lookup later
}

class I2CDeviceManager:
    def __init__(self):
        self.device_instances: Dict[str, Any] = {}
        self.config: Dict[str, Any] = {"connections": [], "new_connections": [], "archived_connections": []}
        self.load_config()

    def load_config(self):
        global self.config
        try:
            with open(CONFIG_FILE, 'r') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.save_config()

    def save_config(self):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)

    def scan_i2c_bus(self) -> List[str]:
        bus = smbus.SMBus(1)
        devices = []
        for addr in range(128):
            try:
                bus.read_byte(addr)
                devices.append(hex(addr))
            except:
                pass
        return devices

    def refresh_device_list(self):
        """One-time scan + update config (new/removed devices). Called by tools."""
        current_devices = self.scan_i2c_bus()
        self.load_config()

        # Handle removed devices
        for conn in self.config['connections'][:]:
            if conn['address'] not in current_devices and conn.get('active'):
                conn['active'] = 0
                self.config['archived_connections'].append(conn)
                self.config['connections'].remove(conn)
                self.device_instances.pop(conn['address'], None)

        # Handle re-connected archived devices
        for conn in self.config['archived_connections'][:]:
            if conn['address'] in current_devices and not conn.get('active', 0):
                conn['active'] = 1
                self.config['connections'].append(conn)
                self.config['archived_connections'].remove(conn)
                self.initialize_device(conn)

        # Detect brand-new devices
        known = {c['address'] for c in self.config['connections'] + self.config['archived_connections']}
        for addr in current_devices:
            if addr not in known:
                self.config['new_connections'].append({
                    "address": addr,
                    "name": "Unknown Device",
                    "interface_module": "",
                    "interface_class": "",
                    "active": 0
                })

        self.save_config()
        logger.info(f"Refreshed I2C devices. Current: {len(self.config['connections'])} | New: {len(self.config['new_connections'])}")

    def initialize_device(self, conn: Dict):
        if not conn.get('active') or conn['address'] in self.device_instances:
            return
        if not conn.get('interface_module') or not conn.get('interface_class'):
            logger.warning(f"Device {conn['address']} missing interface_module/class")
            return
        try:
            module = importlib.import_module(f"interfaces.{conn['interface_module']}")
            device_class = getattr(module, conn['interface_class'])
            addr_int = int(conn['address'], 16)
            self.device_instances[conn['address']] = device_class(address=addr_int)
            logger.info(f"Initialized {conn['name']} at {conn['address']}")
        except Exception as e:
            logger.error(f"Failed to init {conn['address']}: {e}")

    def read_device(self, address: str) -> Dict:
        self.initialize_device(next((c for c in self.config['connections'] if c['address'] == address), {}))
        if address in self.device_instances:
            try:
                return self.device_instances[address].read()
            except Exception as e:
                return {"error": str(e)}
        return {"error": f"Device {address} not initialized or not active"}

    def write_device(self, address: str, value: int, channel: Optional[int] = None):
        self.initialize_device(next((c for c in self.config['connections'] if c['address'] == address), {}))
        if address in self.device_instances:
            try:
                if channel is not None:
                    self.device_instances[address].write(value, channel)
                else:
                    self.device_instances[address].write(value)
                logger.info(f"Wrote {value} to {address} (channel {channel})")
            except Exception as e:
                logger.error(f"Write error: {e}")

    def get_common_suggestions(self, address: str) -> List[str]:
        return COMMON_I2C_DEVICES.get(address, ["Unknown — provide model number for interface generation"])

    def update_device_config(self, address: str, name: str, interface_module: str, interface_class: str,
                             ui_components: Optional[List[Dict]] = None, read_interval: Optional[float] = None):
        self.load_config()
        updated = {
            "address": address,
            "name": name,
            "interface_module": interface_module,
            "interface_class": interface_class,
            "ui_components": ui_components or [],
            "active": 1
        }
        if read_interval is not None:
            updated["read_interval"] = read_interval

        # Add to connections (or move from new_connections)
        section = 'new_connections' if any(c['address'] == address for c in self.config['new_connections']) else 'connections'
        for i, c in enumerate(self.config[section]):
            if c['address'] == address:
                self.config[section][i] = updated
                break
        else:
            self.config['connections'].append(updated)

        if section == 'new_connections':
            self.config['new_connections'] = [c for c in self.config['new_connections'] if c['address'] != address]

        self.save_config()
        self.initialize_device(updated)
        logger.info(f"Configured device {address} as {name}")


# ========================= MCP SERVER =========================
manager = I2CDeviceManager()
mcp = FastMCP("I2C Device Manager MCP Server")

@mcp.tool()
def list_connected_devices() -> Dict:
    """Return current active, new, and archived devices (LLM-friendly JSON)."""
    manager.refresh_device_list()
    return {
        "connections": manager.config["connections"],
        "new_connections": manager.config["new_connections"],
        "archived_connections": manager.config["archived_connections"]
    }

@mcp.tool()
def scan_and_detect_new_devices() -> Dict:
    """Scan bus, detect unknowns, and give LLM suggestions to ask the user."""
    manager.refresh_device_list()
    new_devices = manager.config["new_connections"]
    suggestions = {dev["address"]: manager.get_common_suggestions(dev["address"]) for dev in new_devices}
    return {
        "new_devices_detected": new_devices,
        "common_suggestions": suggestions,
        "llm_instruction": "Relay these suggestions to the user and confirm the exact model before calling configure_device."
    }

@mcp.tool()
def read_device_data(address: str) -> Dict:
    """Read latest sensor/actuator data from the device."""
    data = manager.read_device(address)
    return {"address": address, "data": data}

@mcp.tool()
def write_device_data(address: str, value: int, channel: Optional[int] = None) -> str:
    """Write value (e.g. servo angle) to device/channel."""
    manager.write_device(address, value, channel)
    return f"Write successful: value={value} to {address} (channel={channel})"

@mcp.tool()
def configure_device(address: str, name: str, interface_module: str, interface_class: str,
                     ui_components: Optional[List[Dict]] = None, read_interval: Optional[float] = None) -> str:
    """Add or update device config after user confirmation."""
    manager.update_device_config(address, name, interface_module, interface_class, ui_components, read_interval)
    return f"Device {address} configured as '{name}' with interface {interface_module}.{interface_class}"

@mcp.tool()
def list_available_interfaces() -> List[str]:
    """List all interface modules available for new devices."""
    return [f[:-3] for f in os.listdir("interfaces") if f.endswith(".py") and f != "base.py"]

@mcp.tool()
def get_interface_code(module_name: str) -> str:
    """Return full source of an existing interface (for LLM editing)."""
    path = f"interfaces/{module_name}.py"
    if os.path.exists(path):
        with open(path, "r") as f:
            return f.read()
    return f"ERROR: {module_name} not found"

@mcp.tool()
def save_interface_code(module_name: str, code: str) -> str:
    """Save LLM-generated interface class. Then call configure_device."""
    path = f"interfaces/{module_name}.py"
    with open(path, "w") as f:
        f.write(code)
    return f"Interface {module_name}.py saved successfully. Ready for configure_device."

@mcp.tool()
def get_interface_template(device_model: str) -> str:
    """LLM-friendly template + instructions to build a new interface class."""
    template = f"""from .base import DeviceInterface
# import your library here (e.g. import some_lib)

class {device_model.replace(' ', '').replace('-', '')}Interface(DeviceInterface):
    def __init__(self, address):
        super().__init__(address)
        # self.device = some_lib.Device(address=address)   # or whatever the lib needs

    def read(self):
        \"\"\"Return dict of readable values (must match ui_components data_key).\"\"\"
        # Implement sensor read here
        return {{"example_key": 0.0}}

    def write(self, value: int, channel: Optional[int] = None):
        \"\"\"Optional: implement for actuators (servos, etc.).\"\"\"
        pass

# After implementing, call save_interface_code with the FULL code above.
# Then use configure_device with the new module/class name.
"""
    return template

if __name__ == "__main__":
    # First scan on startup
    manager.refresh_device_list()
    logger.info("I2C MCP Server ready — LLM clients can now connect!")
    mcp.run()  # stdio transport by default (perfect for MCP clients)
