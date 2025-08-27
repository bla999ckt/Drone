"""
Safety monitoring system for the drone delivery operations
"""

import logging
from datetime import datetime
import math
from geopy.distance import geodesic
import json

class SafetyMonitor:
    def __init__(self):
        self.logger = logging.getLogger('safety_monitor')
        self.safety_limits = {
            'min_battery': 20,  # Minimum battery percentage for mission
            'max_wind_speed': 25,  # Maximum wind speed in km/h
            'max_distance': 10,  # Maximum delivery distance in km
            'min_altitude': 30,  # Minimum safe altitude in meters
            'max_altitude': 120,  # Maximum legal altitude in meters
            'no_fly_zones': []  # List of no-fly zone coordinates
        }
        
    def load_no_fly_zones(self, filename):
        """Load no-fly zones from a JSON file"""
        try:
            with open(filename, 'r') as f:
                self.safety_limits['no_fly_zones'] = json.load(f)
            self.logger.info(f"Loaded {len(self.safety_limits['no_fly_zones'])} no-fly zones")
        except Exception as e:
            self.logger.error(f"Failed to load no-fly zones: {e}")
    
    def check_battery_safety(self, battery_level, mission_distance):
        """Check if battery level is sufficient for the mission"""
        # Calculate required battery based on distance
        required_battery = (mission_distance * 2) + self.safety_limits['min_battery']
        
        if battery_level < required_battery:
            self.logger.warning(f"Insufficient battery for mission: {battery_level}% < {required_battery}%")
            return False
        return True
    
    def check_weather_safety(self, wind_speed, visibility):
        """Check if weather conditions are safe for flight"""
        if wind_speed > self.safety_limits['max_wind_speed']:
            self.logger.warning(f"Wind speed too high: {wind_speed} km/h")
            return False
        if visibility < 5000:  # 5km visibility minimum
            self.logger.warning(f"Poor visibility: {visibility}m")
            return False
        return True
    
    def check_altitude_safety(self, altitude):
        """Check if altitude is within safe limits"""
        if altitude < self.safety_limits['min_altitude']:
            self.logger.warning(f"Altitude too low: {altitude}m")
            return False
        if altitude > self.safety_limits['max_altitude']:
            self.logger.warning(f"Altitude too high: {altitude}m")
            return False
        return True
    
    def check_no_fly_zones(self, current_location, destination):
        """Check if flight path intersects with no-fly zones"""
        for zone in self.safety_limits['no_fly_zones']:
            # Check if path intersects with no-fly zone
            zone_center = (zone['lat'], zone['lon'])
            zone_radius = zone['radius']  # in kilometers
            
            # Check current location
            current_distance = geodesic(
                current_location,
                zone_center
            ).kilometers
            
            if current_distance < zone_radius:
                self.logger.warning(f"Current location in no-fly zone: {zone['name']}")
                return False
                
            # Check destination
            dest_distance = geodesic(
                destination,
                zone_center
            ).kilometers
            
            if dest_distance < zone_radius:
                self.logger.warning(f"Destination in no-fly zone: {zone['name']}")
                return False
                
        return True
    
    def is_mission_safe(self, mission_params):
        """
        Check if mission parameters meet all safety requirements
        
        Args:
            mission_params (dict): Dictionary containing:
                - battery_level: Current battery percentage
                - wind_speed: Current wind speed in km/h
                - visibility: Visibility in meters
                - start_location: (lat, lon) tuple
                - destination: (lat, lon) tuple
                - planned_altitude: Planned cruise altitude in meters
        
        Returns:
            bool: True if mission is safe, False otherwise
        """
        try:
            # Calculate mission distance
            distance = geodesic(
                mission_params['start_location'],
                mission_params['destination']
            ).kilometers
            
            if distance > self.safety_limits['max_distance']:
                self.logger.warning(f"Mission distance exceeds maximum: {distance}km")
                return False
            
            # Run all safety checks
            checks = [
                self.check_battery_safety(
                    mission_params['battery_level'],
                    distance
                ),
                self.check_weather_safety(
                    mission_params['wind_speed'],
                    mission_params['visibility']
                ),
                self.check_altitude_safety(
                    mission_params['planned_altitude']
                ),
                self.check_no_fly_zones(
                    mission_params['start_location'],
                    mission_params['destination']
                )
            ]
            
            return all(checks)
            
        except Exception as e:
            self.logger.error(f"Error in safety check: {e}")
            return False
    
    def log_safety_violation(self, violation_type, details):
        """Log safety violations for analysis"""
        timestamp = datetime.now().isoformat()
        log_entry = {
            'timestamp': timestamp,
            'type': violation_type,
            'details': details
        }
        
        self.logger.error(f"Safety violation: {violation_type}")
        self.logger.error(f"Details: {details}")
        
        # Could also save to database or separate file
        return log_entry
