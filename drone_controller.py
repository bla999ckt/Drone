from dronekit import connect, VehicleMode, LocationGlobalRelative
import time
import math
from pymavlink import mavutil
import logging

class DroneController:
    def __init__(self, connection_string="udp:127.0.0.1:14550"):
        self.connection_string = connection_string
        self.vehicle = None
        self.current_location = None
        self.target_location = None
        self.is_connected = False
        self.logger = logging.getLogger('drone_controller')

    def connect(self):
        """Connect to the drone"""
        try:
            self.vehicle = connect(self.connection_string, wait_ready=True)
            self.is_connected = True
            self.logger.info("Connected to drone")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to drone: {str(e)}")
            return False

    def disconnect(self):
        """Disconnect from the drone"""
        if self.vehicle:
            self.vehicle.close()
            self.is_connected = False
            self.logger.info("Disconnected from drone")

    def get_location(self):
        """Get current drone location"""
        if not self.is_connected:
            return None
        return {
            'lat': self.vehicle.location.global_relative_frame.lat,
            'lon': self.vehicle.location.global_relative_frame.lon,
            'alt': self.vehicle.location.global_relative_frame.alt,
            'heading': self.vehicle.heading
        }

    def set_target_location(self, lat, lon, alt=20):
        """Set target location for the drone"""
        self.target_location = LocationGlobalRelative(lat, lon, alt)
        self.logger.info(f"Target location set to: {lat}, {lon}, {alt}")

    def arm_and_takeoff(self, target_altitude=20):
        """Arm the drone and take off to specified altitude"""
        if not self.is_connected:
            return False

        self.logger.info("Basic pre-arm checks")
        while not self.vehicle.is_armable:
            self.logger.info("Waiting for vehicle to initialize...")
            time.sleep(1)

        self.logger.info("Arming motors")
        self.vehicle.mode = VehicleMode("GUIDED")
        self.vehicle.armed = True

        while not self.vehicle.armed:
            self.logger.info("Waiting for arming...")
            time.sleep(1)

        self.logger.info(f"Taking off to {target_altitude} meters")
        self.vehicle.simple_takeoff(target_altitude)

        while True:
            current_altitude = self.vehicle.location.global_relative_frame.alt
            if current_altitude >= target_altitude * 0.95:
                self.logger.info("Reached target altitude")
                break
            time.sleep(1)

        return True

    def goto_location(self):
        """Move to the target location"""
        if not self.is_connected or not self.target_location:
            return False

        self.logger.info(f"Moving to target location: {self.target_location}")
        self.vehicle.simple_goto(self.target_location)

        while True:
            current_location = self.vehicle.location.global_relative_frame
            target_distance = self.get_distance_metres(
                current_location,
                self.target_location
            )
            
            if target_distance < 1:
                self.logger.info("Reached target location")
                break
            time.sleep(1)

        return True

    def return_to_launch(self):
        """Return to launch location"""
        if not self.is_connected:
            return False

        self.logger.info("Returning to launch")
        self.vehicle.mode = VehicleMode("RTL")
        return True

    def get_distance_metres(self, aLocation1, aLocation2):
        """Calculate distance between two locations in meters"""
        dlat = aLocation2.lat - aLocation1.lat
        dlong = aLocation2.lon - aLocation1.lon
        return math.sqrt((dlat*dlat) + (dlong*dlong)) * 1.113195e5

    def get_status(self):
        """Get current drone status"""
        if not self.is_connected:
            return {
                'connected': False,
                'mode': None,
                'armed': False,
                'location': None
            }

        return {
            'connected': True,
            'mode': self.vehicle.mode.name,
            'armed': self.vehicle.armed,
            'location': self.get_location()
        } 