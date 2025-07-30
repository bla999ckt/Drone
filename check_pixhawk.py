#!/usr/bin/env python3
"""
Simple script to check if Pixhawk is initialized and connected
"""

import sys
import time
from pymavlink import mavutil

def check_pixhawk_status(connection_string):
    """Check if Pixhawk is connected and initialized"""
    try:
        print(f"Attempting to connect to Pixhawk on {connection_string}...")
        
        # Connect to the vehicle
        master = mavutil.mavlink_connection(connection_string, baud=115200)
        
        # Wait for the first heartbeat
        print("Waiting for heartbeat...")
        master.wait_heartbeat()
        
        print("✅ SUCCESS: Connected to Pixhawk!")
        print(f"   System ID: {master.target_system}")
        print(f"   Component ID: {master.target_component}")
        
        # Get system info
        try:
            # Request system info
            master.mav.request_data_stream_send(
                master.target_system,
                master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL,
                1,  # Request rate
                1   # Start
            )
            
            # Wait a bit for data
            time.sleep(2)
            
            # Check if we can get some basic info
            print(f"\nVehicle Status:")
            print(f"   Connection established successfully")
            print(f"   Ready for communication")
            
        except Exception as e:
            print(f"   Warning: Could not get detailed info: {e}")
        
        master.close()
        return True
        
    except Exception as e:
        print(f"❌ ERROR: Failed to connect to Pixhawk")
        print(f"   Error: {str(e)}")
        print(f"\nTroubleshooting tips:")
        print(f"   1. Make sure Pixhawk is powered on")
        print(f"   2. Check USB connection")
        print(f"   3. Make sure no other software is using the port")
        print(f"   4. Try a different USB port")
        print(f"   5. Make sure QGroundControl is not connected")
        return False

def main():
    # Try different possible connection strings
    connection_strings = [
        '/dev/tty.usbmodem14201',
        '/dev/tty.usbmodem14203',
        '/dev/ttyACM0',
        '/dev/ttyUSB0',
        'COM3',  # Windows
        'COM4',  # Windows
    ]
    
    print("🔍 Checking Pixhawk connection...")
    print("=" * 50)
    
    for conn_str in connection_strings:
        print(f"\nTrying: {conn_str}")
        if check_pixhawk_status(conn_str):
            print(f"\n✅ Found working connection: {conn_str}")
            print(f"Use this connection string in your Flask app: {conn_str}")
            return conn_str
    
    print(f"\n❌ No working connection found")
    print(f"Please check your Pixhawk setup and try again")
    return None

if __name__ == "__main__":
    main() 