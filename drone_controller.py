from pymavlink import mavutil
import time
import math
import logging
from geopy.distance import geodesic

class DroneController:
    def __init__(self, connection_string="udp:127.0.0.1:14550"):
        self.connection_string = connection_string
        self.master = None
        self.current_location = None
        self.target_location = None
        self.is_connected = False
        self.logger = logging.getLogger('drone_controller')
        self.last_location = None
        self.last_location_time = None
        self.current_speed = 0.0

    def connect(self):
        """Connect to the drone"""
        try:
            self.master = mavutil.mavlink_connection(self.connection_string, baud=115200)
            self.master.wait_heartbeat()
            self.is_connected = True
            self.logger.info("Connected to drone")
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to drone: {str(e)}")
            return False

    def disconnect(self):
        """Disconnect from the drone"""
        if self.master:
            self.master.close()
            self.is_connected = False
            self.logger.info("Disconnected from drone")

    def get_battery_level(self):
        """Get current battery level percentage"""
        if not self.is_connected:
            return 0
        
        try:
            # Try to get battery status from SYS_STATUS message
            sys_status = self.master.recv_match(type='SYS_STATUS', blocking=False)
            if sys_status and hasattr(sys_status, 'battery_remaining'):
                battery_percent = sys_status.battery_remaining
                self.logger.info(f"Battery level: {battery_percent}%")
                return battery_percent
            
            # Try to get battery voltage from BATTERY_STATUS message
            battery_status = self.master.recv_match(type='BATTERY_STATUS', blocking=False)
            if battery_status and hasattr(battery_status, 'voltages'):
                # Calculate percentage from voltage (approximate)
                voltage = battery_status.voltages[0] / 1000.0  # Convert from mV to V
                # Assuming 3S LiPo: 12.6V = 100%, 10.5V = 0%
                if voltage > 12.6:
                    battery_percent = 100
                elif voltage < 10.5:
                    battery_percent = 0
                else:
                    battery_percent = int(((voltage - 10.5) / (12.6 - 10.5)) * 100)
                
                self.logger.info(f"Battery voltage: {voltage}V, estimated: {battery_percent}%")
                return battery_percent
            
            # If no battery data available, return 100% as default
            self.logger.warning("No battery data available, using default 100%")
            return 100
            
        except Exception as e:
            self.logger.error(f"Error getting battery level: {e}")
            return 100

    def get_location(self):
        """Get current drone location"""
        if not self.is_connected:
            self.logger.error("Drone not connected")
            return None
        
        try:
            # Request multiple data streams
            self.master.mav.request_data_stream_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_POSITION,
                10,  # Request rate (10 Hz)
                1    # Start
            )
            
            self.master.mav.request_data_stream_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_EXTENDED_STATUS,
                10,  # Request rate (10 Hz)
                1    # Start
            )
            
            # Wait a bit for data
            time.sleep(1)
            
            # Try multiple GPS message types
            gps_data = None
            
            # Try GPS_RAW_INT first
            for _ in range(20):  # Try more times
                gps_data = self.master.recv_match(type='GPS_RAW_INT', blocking=False)
                if gps_data and gps_data.lat != 0 and gps_data.lon != 0:
                    # Check if GPS fix is valid (fix_type >= 2 means 2D or 3D fix)
                    if hasattr(gps_data, 'fix_type') and gps_data.fix_type >= 2:
                        break
                    else:
                        self.logger.warning(f"GPS fix type {gps_data.fix_type} is not valid (need >= 2)")
                        gps_data = None
                time.sleep(0.1)
            
            # If no GPS_RAW_INT, try GPS_GLOBAL_ORIGIN
            if not gps_data or gps_data.lat == 0:
                for _ in range(10):
                    gps_data = self.master.recv_match(type='GPS_GLOBAL_ORIGIN', blocking=False)
                    if gps_data and gps_data.lat != 0 and gps_data.lon != 0:
                        break
                    time.sleep(0.1)
            
            # If still no data, try GLOBAL_POSITION_INT
            if not gps_data or gps_data.lat == 0:
                for _ in range(10):
                    gps_data = self.master.recv_match(type='GLOBAL_POSITION_INT', blocking=False)
                    if gps_data and gps_data.lat != 0 and gps_data.lon != 0:
                        break
                    time.sleep(0.1)
            
            if gps_data and gps_data.lat != 0 and gps_data.lon != 0:
                # Handle different GPS message types
                if hasattr(gps_data, 'lat') and hasattr(gps_data, 'lon'):
                    lat = gps_data.lat / 1e7  # Convert from degrees * 1e7
                    lon = gps_data.lon / 1e7
                    
                    # Handle altitude from different message types
                    if hasattr(gps_data, 'alt'):
                        alt_mm = gps_data.alt
                        alt_meters = alt_mm / 1000.0
                    elif hasattr(gps_data, 'relative_alt'):
                        alt_meters = gps_data.relative_alt / 1000.0
                    else:
                        alt_meters = 0
                    
                    # Sanity check: if altitude is > 1000m, it's probably wrong
                    if alt_meters > 1000:
                        self.logger.warning(f"Altitude {alt_meters}m seems too high, using 0")
                        alt_meters = 0
                    
                    self.logger.info(f"GPS Data: Lat={lat:.6f}, Lon={lon:.6f}, Alt={alt_meters:.1f}m")
                    
                    return {
                        'lat': lat,
                        'lon': lon,
                        'alt': alt_meters,
                        'heading': 0  # We'll get this separately if needed
                    }
            
            self.logger.warning("No valid GPS data received after trying multiple message types")
            return None
                
        except Exception as e:
            self.logger.error(f"Error getting location: {e}")
            return None

    def get_speed(self):
        """Get current drone speed in m/s"""
        if not self.is_connected:
            return 0.0
        
        try:
            # Try to get VFR_HUD message which contains speed
            vfr_hud = self.master.recv_match(type='VFR_HUD', blocking=False)
            if vfr_hud and hasattr(vfr_hud, 'airspeed'):
                self.current_speed = vfr_hud.airspeed
                return self.current_speed
            
            # If no VFR_HUD, calculate speed from position changes
            return self.calculate_speed_from_position()
            
        except Exception as e:
            self.logger.error(f"Error getting speed: {e}")
            return 0.0

    def calculate_speed_from_position(self):
        """Calculate speed from position changes over time"""
        current_location = self.get_location()
        current_time = time.time()
        
        if not current_location or not self.last_location or not self.last_location_time:
            self.last_location = current_location
            self.last_location_time = current_time
            return 0.0
        
        # Calculate time difference
        time_diff = current_time - self.last_location_time
        
        if time_diff < 0.1:  # Too small time difference
            return self.current_speed
        
        # Calculate distance moved
        distance = geodesic(
            (self.last_location['lat'], self.last_location['lon']),
            (current_location['lat'], current_location['lon'])
        ).meters
        
        # Calculate speed in m/s
        speed = distance / time_diff
        
        # Sanity check: if speed is > 100 m/s, it's probably invalid GPS data
        if speed > 100:
            self.logger.warning(f"Calculated speed {speed} m/s is too high, using 0")
            speed = 0.0
        
        # Update last position
        self.last_location = current_location
        self.last_location_time = current_time
        self.current_speed = speed
        
        return speed

    def set_target_location(self, lat, lon, alt=20):
        """Set target location for the drone"""
        self.target_location = {'lat': lat, 'lon': lon, 'alt': alt}
        self.logger.info(f"Target location set to: {lat}, {lon}, {alt}")

    def arm_and_takeoff(self, target_altitude=20):
        """Arm the drone and take off to specified altitude"""
        if not self.is_connected:
            return False

        try:
            self.logger.info("Basic pre-arm checks")
            
            # Set mode to GUIDED
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_DO_SET_MODE,
                0, 0, 4, 0, 0, 0, 0, 0)  # GUIDED mode
            
            time.sleep(2)
            
            # Arm the drone
            self.logger.info("Arming motors")
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
                0, 1, 0, 0, 0, 0, 0, 0)
            
            time.sleep(3)
            
            # Take off
            self.logger.info(f"Taking off to {target_altitude} meters")
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
                0, 0, 0, 0, 0, 0, 0, target_altitude)
            
            # Wait for takeoff
            time.sleep(10)
            
            self.logger.info("Takeoff sequence completed")
            return True
            
        except Exception as e:
            self.logger.error(f"Error in arm_and_takeoff: {e}")
            return False

    def goto_location(self, lat=None, lon=None, alt=None):
        """Move to the target location"""
        if not self.is_connected:
            return False

        try:
            # Use provided coordinates or stored target
            if lat is not None and lon is not None:
                target_lat, target_lon = lat, lon
            elif self.target_location:
                target_lat, target_lon = self.target_location['lat'], self.target_location['lon']
            else:
                self.logger.error("No target location set")
                return False
            
            target_alt = alt if alt is not None else (self.target_location['alt'] if self.target_location else 20)
            
            self.logger.info(f"Moving to target location: {target_lat}, {target_lon}, {target_alt}")
            
            # Send waypoint command
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                0, 0, 0, 0, 0, 0, target_lat, target_lon)
            
            # Wait for movement
            time.sleep(5)
            
            self.logger.info("Movement command sent")
            return True
            
        except Exception as e:
            self.logger.error(f"Error in goto_location: {e}")
            return False

    def return_to_launch(self):
        """Return to launch location"""
        if not self.is_connected:
            return False

        try:
            self.logger.info("Returning to launch")
            self.master.mav.command_long_send(
                self.master.target_system,
                self.master.target_component,
                mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
                0, 0, 0, 0, 0, 0, 0, 0)
            
            time.sleep(2)
            return True
            
        except Exception as e:
            self.logger.error(f"Error in return_to_launch: {e}")
            return False

    def get_distance_metres(self, aLocation1, aLocation2):
        """Calculate distance between two locations in meters"""
        dlat = aLocation2['lat'] - aLocation1['lat']
        dlong = aLocation2['lon'] - aLocation1['lon']
        return math.sqrt((dlat*dlat) + (dlong*dlong)) * 1.113195e5 