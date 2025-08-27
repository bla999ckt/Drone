# configuration for Blood Delivery Drone System

# Pixhawk connection string (update as needed)
CONNECTION_STRING = '/dev/ttyACM0'

# Default hospital location 
DEFAULT_HOSPITAL = {
    'name': 'Example Hospital',
    'latitude': 39.9042,
    'longitude': 116.4074
}

# Default home location for drone (where it returns if no missions)
HOME_LOCATION = {
    'name': 'Drone Home',
    'latitude': 40.7128,
    'longitude': -74.0060
}

# Path to no-fly zones JSON file
NO_FLY_ZONES_PATH = 'instance/no_fly_zones.json'

