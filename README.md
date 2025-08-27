# Blood Delivery Drone System

A Flask-based web application for managing blood inventory and delivery between hospitals using drones.

## Features
- Hospital management system
- Blood inventory tracking
- Blood request management
- Real-time drone status and location monitoring
- Interactive map interface
- Mission planning and safety monitoring
- Pixhawk integration for autonomous delivery

## Quick Start
1. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Initialize the database:
   ```bash
   python seed_db.py
   ```
4. Run the application:
   ```bash
   python app.py
   ```
   The app will be available at [http://localhost:5000](http://localhost:5000)

## Project Structure

- `app.py`: Main Flask application
- `seed_db.py`: Database initialization script
- `templates/`: HTML templates
- `static/`: Static files (CSS, JS, images)
- `blood_inventory.db`: SQLite database file

## Database Schema

### Hospitals
- id (Primary Key)
- name
- latitude
- longitude

### Blood Inventory
- id (Primary Key)
- hospital_id (Foreign Key)
- blood_type
- units
- last_updated

## Development Status

### Current Phase
- Basic web interface
- Hospital management
- Blood inventory tracking
- Sample data seeding

### Next Steps
- Drone integration
- Real-time tracking
- Automated delivery scheduling
- Weather monitoring
- Safety protocols

## Notes

- The current version uses a demo database with sample hospitals and blood inventory
- Hospitals can update their inventory through the web interface
- The drone integration is planned for future development

# Raspberry Pi / Orange Pi Setup Guide

## Hardware Requirements
- Raspberry Pi 4/3 or Orange Pi (with Raspbian/Debian/Ubuntu)
- MicroSD card (16GB+ recommended)
- Power supply
- WiFi/Ethernet connection
- USB cable for Pixhawk connection

## Software Setup
1. **Update your system:**
   ```sh
   sudo apt update && sudo apt upgrade
   ```
2. **Install Python 3 and pip:**
   ```sh
   sudo apt install python3 python3-pip
   ```
3. **Clone the repository:**
   ```sh
   git clone https://github.com/<your-repo>/Drone.git
   cd Drone
   ```
4. **Install dependencies:**
   ```sh
   pip3 install -r requirements.txt
   ```
5. **Connect Pixhawk:**
   - Plug Pixhawk into USB port.
   - Find the device path (usually `/dev/ttyACM0`, `/dev/ttyUSB0`, or similar).
   - Update `connection_string` in `app.py` if needed.

## Running the Flask App as a Server
1. **Start the app:**
   ```sh
   python3 app.py
   ```
   - The app will be available at `http://<raspberrypi-ip>:5000` for everyone on the network.
2. **Make it accessible to everyone:**
   - Ensure your Pi has a static IP or is discoverable on your network.
   - Open port 5000 in your firewall/router if needed.
   - Others can access the dashboard via browser: `http://<raspberrypi-ip>:5000`

## Tips
- For public access, consider using port forwarding or a reverse proxy (e.g., Nginx).
- Use `screen` or `tmux` to keep the server running in the background.
- For production, disable debug mode and secure your Pi.

See `docs/DRONE_GUIDE.md` for advanced setup and troubleshooting.

## Deploying on Raspberry Pi or Orange Pi

You can run this Flask app on a Raspberry Pi or Orange Pi to make it accessible to everyone on your local network. This is ideal for real-world drone operations.

### Hardware Requirements
- Raspberry Pi 3/4 or Orange Pi (with WiFi/Ethernet)
- MicroSD card (16GB+ recommended)
- Power supply
- Pixhawk flight controller (connected via USB)

### Software Setup
1. **Install Raspberry Pi OS (or Armbian for Orange Pi)**
2. **Connect to WiFi or Ethernet**
3. **Update system packages:**
   ```sh
   sudo apt update && sudo apt upgrade -y
   ```
4. **Install Python 3 and pip:**
   ```sh
   sudo apt install python3 python3-pip -y
   ```
5. **Clone the project:**
   ```sh
   git clone https://github.com/yourusername/Drone.git
   cd Drone
   ```
6. **Install dependencies:**
   ```sh
   pip3 install -r requirements.txt
   ```
7. **Connect Pixhawk via USB**
   - Find the device path (e.g., `/dev/ttyACM0` or `/dev/ttyUSB0`).
   - Update `app.py` with the correct `connection_string`.

### Running the Server for Everyone
- Start the Flask app so it's accessible to all devices on your network:
  ```sh
  python3 app.py
  ```
- The app will be available at `http://<raspberrypi_ip>:5000`.
- To find your Pi's IP address:
  ```sh
  hostname -I
  ```
- Access the dashboard from any device on the same network using the Pi's IP.

### Tips for Reliable Deployment
- Use a static IP for your Pi for easier access.
- Consider running the app with `nohup` or as a systemd service for auto-restart.
- Ensure your firewall allows traffic on port 5000.
- For remote access, set up port forwarding or use a VPN (advanced).

### Troubleshooting
- If you can't access the app, check your Pi's IP and network connection.
- Make sure Pixhawk is properly connected and detected.
- Review logs in `drone_operations.log` for errors.

For more details, see `docs/DRONE_GUIDE.md`.

## Configuration Setup

Before running the app, edit `instance/config.py` to set your Pixhawk connection string and default hospital location. Example:

```python
CONNECTION_STRING = '/dev/ttyACM0'  # Update for your Pixhawk device
DEFAULT_HOSPITAL = {
    'name': 'Your Hospital',
    'latitude': 12.3456,
    'longitude': 78.9012
}
```

## Setting Home Location and No-Fly Zones

- Edit `HOME_LOCATION` in `instance/config.py` to set where your drone returns when idle.
- Edit or replace `instance/no_fly_zones.json` to define restricted areas. Example:

```python
HOME_LOCATION = {
    'name': 'Drone Home',
    'latitude': 40.7128,
    'longitude': -74.0060
}
```

Example `no_fly_zones.json`:
```json
[
    {"name": "Airport Zone", "lat": 40.6413, "lon": -73.7781, "radius_km": 5},
    {"name": "City Center", "lat": 40.7128, "lon": -74.0060, "radius_km": 2}
]
```

Refer to `docs/DRONE_GUIDE.md` for more details.


