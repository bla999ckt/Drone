#!/usr/bin/env python3
"""
Comprehensive test script for Pixhawk connection and functionality
"""

import sys
import time
from pymavlink import mavutil
import argparse
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_connection(connection_string):
    """Test Pixhawk connection and basic functionality"""
    try:
        logger.info(f"Attempting to connect to Pixhawk on {connection_string}...")
        
        # Connect to the vehicle
        master = mavutil.mavlink_connection(connection_string, baud=115200)
        
        # Wait for the first heartbeat
        logger.info("Waiting for heartbeat...")
        master.wait_heartbeat()
        
        logger.info("✅ Connected to Pixhawk!")
        logger.info(f"System ID: {master.target_system}")
        logger.info(f"Component ID: {master.target_component}")
        
        # Request data streams
        master.mav.request_data_stream_send(
            master.target_system,
            master.target_component,
            mavutil.mavlink.MAV_DATA_STREAM_ALL,
            4,  # Request rate
            1   # Start
        )
        
        # Wait for data
        time.sleep(2)
        
        # Test battery status
        msg = master.recv_match(type='SYS_STATUS', blocking=True, timeout=2)
        if msg:
            battery_remaining = msg.battery_remaining
            logger.info(f"Battery Level: {battery_remaining}%")
        else:
            logger.warning("Could not get battery status")
        
        # Test GPS status
        msg = master.recv_match(type='GPS_RAW_INT', blocking=True, timeout=2)
        if msg:
            fix_type = msg.fix_type
            logger.info(f"GPS Fix Type: {fix_type}")
            if msg.lat and msg.lon:
                lat = msg.lat / 1e7  # Convert from * 10^7
                lon = msg.lon / 1e7
                logger.info(f"Location: Lat {lat}, Lon {lon}")
        else:
            logger.warning("Could not get GPS status")
        
        # Test armed status
        msg = master.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
        if msg:
            armed = msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
            logger.info(f"Armed Status: {'ARMED' if armed else 'DISARMED'}")
        else:
            logger.warning("Could not get armed status")
            
        # Test flight mode
        if msg:
            flight_mode = mavutil.mode_string_v10(msg)
            logger.info(f"Flight Mode: {flight_mode}")
        
        master.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Connection failed: {str(e)}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Test Pixhawk connection and functionality')
    parser.add_argument('--port', default='/dev/tty.usbmodem14203',
                      help='Connection string (e.g., /dev/ttyACM0 or /dev/tty.usbmodem14203)')
    args = parser.parse_args()
    
    if test_connection(args.port):
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == '__main__':
    main()
