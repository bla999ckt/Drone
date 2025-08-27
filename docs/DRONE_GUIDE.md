# Drone Setup & Integration Guide

## Setting Up Pixhawk for Blood Delivery

1. **Hardware Assembly**
   - Connect Pixhawk 6X to your computer via USB.
   - Attach GPS module and telemetry radio if available.
   - Power Pixhawk with a battery or USB.

2. **Software Installation**
   - Install [QGroundControl](https://docs.qgroundcontrol.com/master/en/getting_started/download_and_install.html) for initial configuration.
   - Optionally, install [Mission Planner](https://ardupilot.org/planner/) for advanced mission planning.

3. **Basic Configuration**
   - Open QGroundControl and follow the setup wizard:
     - Calibrate sensors
     - Configure flight modes
     - Set up failsafe procedures
     - Configure GPS

## Linking Pixhawk to the Flask App

1. **Install Python Dependencies**
   - In your project directory, run:

     ```bash
     pip install -r requirements.txt
     ```

2. **Connect Pixhawk to Flask**
   - Ensure Pixhawk is connected via USB (e.g., `/dev/tty.usbmodem14203` on macOS).
   - In `app.py`, the drone controller is initialized:

     ```python
     drone = DroneController(connection_string='/dev/tty.usbmodem14203')
     ```

3. **Test Connection**
   - Use the web interface or run:

     ```bash
     python test_connection.py --port /dev/tty.usbmodem14203
     ```
   - Confirm connection and heartbeat.

4. **Run the Flask App**
   - Start the server:

     ```bash
     python app.py
     ```
   - Open [http://localhost:5000](http://localhost:5000) in your browser.

## What You Can Test With Pixhawk Alone
- Connection and status monitoring
- Battery and GPS reporting
- Mission planning and selection
- Command simulation (arming, takeoff, waypoint)
- Safety checks and logs

## Safety & Best Practices
- Always check battery, GPS, and weather before flight.
- Use the web dashboard to monitor status and logs.
- Follow local regulations and register your drone.

## Raspberry Pi / Orange Pi Deployment

This guide explains how to set up the Blood Delivery Drone System on a Raspberry Pi or Orange Pi and make it accessible to everyone on your network.

### Hardware Needed
- Raspberry Pi 3/4 or Orange Pi
- MicroSD card (16GB+)
- Power supply
- Pixhawk flight controller (USB connection)

### Software Setup
1. **Install OS:** Use Raspberry Pi OS (for Pi) or Armbian (for Orange Pi).
2. **Connect to Internet:** WiFi or Ethernet.
3. **Update system:**
   ```sh
   sudo apt update && sudo apt upgrade -y
   ```
4. **Install Python 3 and pip:**
   ```sh
   sudo apt install python3 python3-pip -y
   ```
5. **Clone the repository:**
   ```sh
   git clone https://github.com/yourusername/Drone.git
   cd Drone
   ```
6. **Install Python dependencies:**
   ```sh
   pip3 install -r requirements.txt
   ```
7. **Connect Pixhawk:**
   - Plug Pixhawk into USB.
   - Find device path (e.g., `/dev/ttyACM0`).
   - Update `app.py` with correct `connection_string`.

### Running the Flask App as a Server
- Start the app so it's accessible to everyone:
  ```sh
  python3 app.py
  ```
- Find your Pi's IP address:
  ```sh
  hostname -I
  ```
- Access the dashboard from any device on the network at `http://<raspberrypi_ip>:5000`

### Best Practices
- Set a static IP for your Pi.
- Use `nohup` or systemd for auto-restart.
- Open port 5000 in your firewall.
- For remote access, use port forwarding or VPN (advanced).

### Troubleshooting
- Can't access app? Check IP, network, and firewall.
- Pixhawk not detected? Check USB connection and permissions.
- See `drone_operations.log` for errors.

## Configuration Instructions

Edit `instance/config.py` to set your Pixhawk connection string and hospital location. For example:

```python
CONNECTION_STRING = '/dev/ttyACM0'  # Use your device path
DEFAULT_HOSPITAL = {
    'name': 'Your Hospital',
    'latitude': 12.3456,
    'longitude': 78.9012
}
```

- Find your Pixhawk device path by running `ls /dev/tty*` after plugging it in.
- Set your hospital's coordinates and name.
- Save the file and start the app.

# Home Location & No-Fly Zones Setup

- Set your drone's home location in `instance/config.py` under `HOME_LOCATION`.
- Define no-fly zones in `instance/no_fly_zones.json` (edit or replace the example).

Example home location:
```python
HOME_LOCATION = {
    'name': 'Drone Home',
    'latitude': 40.7128,
    'longitude': -74.0060
}
```

Example no-fly zones:
```json
[
    {"name": "Airport Zone", "lat": 40.6413, "lon": -73.7781, "radius_km": 5},
    {"name": "City Center", "lat": 40.7128, "lon": -74.0060, "radius_km": 2}
]
```

- Save your changes and restart the app.
- For more details, see the rest of this guide.

---

This guide ensures anyone can set up and run the Blood Delivery Drone System on a Raspberry Pi/Orange Pi, making it accessible as a server for everyone on the network.

For more details, see the official documentation and community forums in the resources section.

## MAVLink Mission Commands: How Missions Are Sent to Pixhawk

When a blood delivery mission is scheduled, the Flask backend sends a series of MAVLink commands to Pixhawk using the `DroneController` class. Here’s how it works:

### Command Sequence
1. **Arm and Takeoff**
   - Command: `MAV_CMD_COMPONENT_ARM_DISARM` (arm motors)
   - Command: `MAV_CMD_NAV_TAKEOFF` (take off to target altitude)
2. **Fly to Source Hospital**
   - Command: `MAV_CMD_NAV_WAYPOINT` (fly to source hospital coordinates)
3. **Fly to Destination Hospital**
   - Command: `MAV_CMD_NAV_WAYPOINT` (fly to destination hospital coordinates)
4. **Return to Launch**
   - Command: `MAV_CMD_NAV_RETURN_TO_LAUNCH` (return to home/base)

### Example Python Code
```python
# Arm and takeoff
self.master.mav.command_long_send(
    self.master.target_system,
    self.master.target_component,
    mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
    0, 1, 0, 0, 0, 0, 0, 0)
self.master.mav.command_long_send(
    self.master.target_system,
    self.master.target_component,
    mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
    0, 0, 0, 0, 0, 0, 0, target_altitude)

# Fly to waypoint
self.master.mav.command_long_send(
    self.master.target_system,
    self.master.target_component,
    mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
    0, 0, 0, 0, 0, 0, lat, lon)

# Return to launch
self.master.mav.command_long_send(
    self.master.target_system,
    self.master.target_component,
    mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
    0, 0, 0, 0, 0, 0, 0, 0)
```

### How Pixhawk Interprets These Commands
- **Arm/Disarm:** Pixhawk arms the motors, preparing for flight.
- **Takeoff:** Pixhawk takes off to the specified altitude.
- **Waypoint:** Pixhawk navigates to the given GPS coordinates.
- **Return to Launch:** Pixhawk returns to its home location and lands.

### Safety & Error Handling
- The backend checks for invalid missions (e.g., source and destination are the same) and will not send commands in such cases.
- The safety monitor checks for no-fly zones before sending commands.
- All actions and errors are logged in `drone_operations.log` for review.

See `drone_controller.py` for full implementation details.

## Cellular/Remote MAVLink Control: SIM Card and Pixhawk

**Can you put a SIM card in Pixhawk?**
- No, Pixhawk does not have a SIM card slot or built-in cellular modem.
- Pixhawk only receives MAVLink commands via USB, telemetry radio, or serial ports.

**How to send MAVLink commands remotely using cellular (SIM card):**
- Use a companion computer (e.g., Raspberry Pi or Orange Pi) with a cellular modem/SIM card.
- The companion computer connects to Pixhawk via USB or serial and runs the Flask app or MAVLink relay.
- Your PC or server sends MAVLink commands over the internet to the companion computer.
- The companion computer relays commands to Pixhawk, which executes them as usual.

**Typical setup:**
1. Insert SIM card into a 4G/LTE USB modem or HAT on Raspberry Pi/Orange Pi.
2. Connect Pi to Pixhawk via USB/serial.
3. Run the Flask app or MAVProxy on the Pi.
4. Send commands from your PC/server to the Pi (using public IP, VPN, or reverse SSH).
5. Pi relays MAVLink commands to Pixhawk.

**Summary:**
- SIM card goes in the companion computer, not Pixhawk.
- Pixhawk acts on MAVLink commands received from the companion computer.
- This enables remote control and telemetry over cellular networks.

For more details, see the companion computer and MAVProxy documentation.