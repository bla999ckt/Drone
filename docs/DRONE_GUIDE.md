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