from gevent import monkey
monkey.patch_all()

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit
from datetime import datetime
import logging
from geopy.distance import geodesic
import os
import json
import threading
import time
import re

# Import drone controller and safety monitor
from drone_controller import DroneController
from safety_monitor import SafetyMonitor

# Configure logging
logging.basicConfig(
    filename='drone_operations.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blood_inventory.db'
db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode='gevent')

# Load configuration from instance/config.py
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'instance'))
try:
    import config
except ImportError:
    config = None

# Use config values if available, otherwise fallback to example
connection_string = getattr(config, 'CONNECTION_STRING', '/dev/tty.usbmodem14203')
home_location = getattr(config, 'HOME_LOCATION', {'name': 'Drone Home', 'latitude': 40.7128, 'longitude': -74.0060})
no_fly_zones_path = getattr(config, 'NO_FLY_ZONES_PATH', 'instance/no_fly_zones.json')

drone = DroneController(connection_string=connection_string)

# Initialize safety monitor
safety_monitor = SafetyMonitor()
if os.path.exists(no_fly_zones_path):
    safety_monitor.load_no_fly_zones(no_fly_zones_path)

# Database Models (must be defined before any routes/functions that use them)
class Hospital(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    blood_inventory = db.relationship('BloodInventory', backref='hospital', lazy=True)

class BloodInventory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital.id'), nullable=False)
    blood_type = db.Column(db.String(5), nullable=False)
    units = db.Column(db.Integer, nullable=False)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

class BloodRequest(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey('hospital.id'), nullable=False)
    blood_type = db.Column(db.String(5), nullable=False)
    units = db.Column(db.Integer, nullable=False)
    urgency = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), default='pending')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    hospital = db.relationship('Hospital', backref='blood_requests')

# Global variables for mission tracking
current_mission = None
mission_start_time = None
mission_start_location = None
drone_status = {
    'is_charging': False,
    'battery_level': 100,
    'is_available': True,
    'current_location': None
}

def get_drone_status():
    """Get comprehensive drone status including battery and charging"""
    global drone_status
    
    if not drone.is_connected:
        drone_status['is_available'] = False
        return drone_status
    
    # Get battery level
    battery = drone.get_battery_level()
    drone_status['battery_level'] = battery
    
    # Determine if charging (battery increasing or connected to power)
    # For now, assume charging if battery > 90% or if we can detect charging
    drone_status['is_charging'] = battery > 90
    
    # Get current location
    location = drone.get_location()
    drone_status['current_location'] = location
    
    # Determine if available for missions
    drone_status['is_available'] = battery > 20 and not drone_status['is_charging']
    
    return drone_status

def select_best_mission():
    """Select the best mission based on drone location, urgency, and availability"""
    global current_mission
    
    # Get drone status
    drone_status = get_drone_status()
    
    # If drone is not available, no mission
    if not drone_status['is_available']:
        return None
    
    # Get all pending blood requests
    pending_requests = BloodRequest.query.filter_by(status='pending').order_by(
        BloodRequest.created_at.asc()
    ).all()
    
    if not pending_requests:
        return None
    
    # Get available blood inventory
    available_inventory = BloodInventory.query.filter(
        BloodInventory.units > 0
    ).all()
    
    if not available_inventory:
        return None
    
    # Create mission candidates
    mission_candidates = []
    
    for request in pending_requests:
        requesting_hospital = Hospital.query.get(request.hospital_id)
        
        # Find hospitals with required blood
        available_hospitals = []
        for inv in available_inventory:
            if inv.blood_type == request.blood_type and inv.units >= request.units:
                hospital = Hospital.query.get(inv.hospital_id)
                available_hospitals.append(hospital)
        
        if not available_hospitals:
            continue
        
        # Calculate distances and create mission candidates
        for source_hospital in available_hospitals:
            # Distance from drone to source hospital
            drone_to_source = None
            if drone_status['current_location']:
                drone_to_source = geodesic(
                    (drone_status['current_location']['lat'], drone_status['current_location']['lon']),
                    (source_hospital.latitude, source_hospital.longitude)
                ).kilometers
            else:
                # If no GPS, assume drone is at first hospital
                drone_to_source = 0
            
            # Distance from source to destination
            source_to_dest = geodesic(
                (source_hospital.latitude, source_hospital.longitude),
                (requesting_hospital.latitude, requesting_hospital.longitude)
            ).kilometers
            
            # Total mission distance
            total_distance = drone_to_source + source_to_dest
            
            # Calculate priority score (lower is better)
            urgency_score = 0
            if request.urgency == 'critical':
                urgency_score = 0
            elif request.urgency == 'urgent':
                urgency_score = 10
            else:
                urgency_score = 20
            
            # Time waiting score (older requests get higher priority)
            time_waiting = (datetime.utcnow() - request.created_at).total_seconds() / 3600  # hours
            time_score = time_waiting * 5  # 5 points per hour waiting
            
            # Distance score (shorter missions get higher priority)
            distance_score = total_distance * 2  # 2 points per km
            
            total_score = urgency_score + time_score + distance_score
            
            mission_candidates.append({
                'request': request,
                'source_hospital': source_hospital,
                'destination_hospital': requesting_hospital,
                'total_distance': total_distance,
                'drone_to_source': drone_to_source,
                'source_to_dest': source_to_dest,
                'priority_score': total_score,
                'blood_type': request.blood_type,
                'units': request.units,
                'urgency': request.urgency
            })
    
    if not mission_candidates:
        return None
    
    # Select mission with lowest priority score (highest priority)
    best_mission = min(mission_candidates, key=lambda m: m['priority_score'])
    
    # Format mission for return
    mission = {
        'id': best_mission['request'].id,
        'from_hospital': {
            'name': best_mission['source_hospital'].name,
            'lat': best_mission['source_hospital'].latitude,
            'lon': best_mission['source_hospital'].longitude
        },
        'to_hospital': {
            'name': best_mission['destination_hospital'].name,
            'lat': best_mission['destination_hospital'].latitude,
            'lon': best_mission['destination_hospital'].longitude
        },
        'blood_type': best_mission['blood_type'],
        'units': best_mission['units'],
        'urgency': best_mission['urgency'],
        'total_distance': best_mission['total_distance'],
        'priority_score': best_mission['priority_score'],
        'request_id': best_mission['request'].id
    }
    
    return mission

def get_current_mission():
    """Get current mission - either active or best available"""
    global current_mission
    
    # If we have an active mission, return it
    if current_mission:
        return current_mission
    
    # Otherwise, select the best available mission
    current_mission = select_best_mission()
    return current_mission

def check_drone_movement():
    """Check if drone is moving based on location changes"""
    global current_mission, mission_start_time, mission_start_location
    
    if not current_mission or not mission_start_location:
        return False
    
    current_location = drone.get_location()
    if not current_location:
        return False
    
    # Calculate distance moved
    distance = geodesic(
        (mission_start_location['lat'], mission_start_location['lon']),
        (current_location['lat'], current_location['lon'])
    ).meters
    
    # Consider moving if moved more than 10 meters
    return distance > 10

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/request-blood', methods=['GET', 'POST'])
def request_blood():
    hospitals = Hospital.query.all()
    if request.method == 'POST':
        hospital_id = request.form.get('hospital_id')
        blood_type = request.form.get('blood_type')
        units = int(request.form.get('units'))
        urgency = request.form.get('urgency')

        if not hospital_id:
            flash('Please select a hospital.', 'error')
            return redirect(url_for('request_blood'))

        request_obj = BloodRequest(
            hospital_id=hospital_id,
            blood_type=blood_type,
            units=units,
            urgency=urgency
        )
        db.session.add(request_obj)
        db.session.commit()

        # Log the request
        logging.info(f"New blood request: Hospital ID {hospital_id}, Blood Type {blood_type}, Units {units}, Urgency {urgency}")
        process_blood_request(request_obj)
        auto_start_mission()  # Automatically start mission if possible
        flash('Blood request submitted successfully!', 'success')
        return redirect(url_for('drone_status'))  # Redirect to status page after order
    return render_template('request_blood.html', hospitals=hospitals)

@app.route('/update-inventory', methods=['GET', 'POST'])
def update_inventory():
    if request.method == 'POST':
        hospital_id = request.form.get('hospital_id')
        blood_type = request.form.get('blood_type')
        units = int(request.form.get('units'))

        inventory = BloodInventory.query.filter_by(
            hospital_id=hospital_id,
            blood_type=blood_type
        ).first()

        if inventory:
            inventory.units = units
            inventory.last_updated = datetime.utcnow()
        else:
            inventory = BloodInventory(
                hospital_id=hospital_id,
                blood_type=blood_type,
                units=units
            )
            db.session.add(inventory)

        db.session.commit()
        logging.info(f"Inventory updated: Hospital ID {hospital_id}, Blood Type {blood_type}, Units {units}")
        emit_mission_queue_update()  # Update queue for all clients
        auto_start_mission()  # Automatically start mission if possible
        flash('Inventory updated successfully!', 'success')
        return redirect(url_for('update_inventory'))

    hospitals = Hospital.query.all()
    return render_template('update_inventory.html', hospitals=hospitals)

@app.route('/view-database')
def view_database():
    hospitals = Hospital.query.all()
    inventory = BloodInventory.query.all()
    requests = BloodRequest.query.all()
    return render_template('view_database.html', 
                         hospitals=hospitals, 
                         inventory=inventory, 
                         requests=requests)

@app.route('/drone-status')
def drone_status_page():
    return render_template('drone_status.html')

@app.route('/debug-gps')
def debug_gps():
    try:
        if not drone.is_connected:
            return jsonify({
                'error': 'Drone not connected'
            })
        
        # Try to get GPS data with detailed logging
        location = drone.get_location()
        
        # Also try to get raw GPS messages
        gps_messages = []
        for _ in range(5):
            try:
                gps_raw = drone.master.recv_match(type='GPS_RAW_INT', blocking=False)
                if gps_raw:
                    gps_messages.append({
                        'lat': gps_raw.lat,
                        'lon': gps_raw.lon,
                        'alt': gps_raw.alt,
                        'fix_type': getattr(gps_raw, 'fix_type', 'unknown'),
                        'satellites_visible': getattr(gps_raw, 'satellites_visible', 'unknown')
                    })
            except:
                pass
            time.sleep(0.1)
        
        return jsonify({
            'connected': drone.is_connected,
            'location': location,
            'gps_messages': gps_messages,
            'message': 'GPS debug info'
        })
        
    except Exception as e:
        return jsonify({
            'error': str(e)
        })

@app.route('/debug-drone')
def debug_drone():
    try:
        # Check if drone is connected
        connected = drone.is_connected
        
        # Try to get location
        location = None
        if connected:
            location = drone.get_location()
        
        # Get connection string
        conn_string = drone.connection_string
        
        return jsonify({
            'connected': connected,
            'connection_string': conn_string,
            'location': location,
            'has_master': drone.master is not None,
            'target_system': drone.master.target_system if drone.master else None,
            'target_component': drone.master.target_component if drone.master else None
        })
    except Exception as e:
        return jsonify({
            'error': str(e),
            'connected': False
        })

@app.route('/connect-drone')
def connect_drone():
    try:
        if drone.connect():
            location = drone.get_location()
            if location:
                return jsonify({
                    'success': True,
                    'message': 'Drone connected successfully',
                    'location': location
                })
            else:
                return jsonify({
                    'success': True,
                    'message': 'Drone connected but no GPS data yet',
                    'location': None
                })
        else:
            return jsonify({
                'success': False,
                'message': 'Failed to connect to drone'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Connection error: {str(e)}'
        })

@app.route('/get-drone-location')
def get_drone_location():
    try:
        if drone.is_connected:
            location = drone.get_location()
            return jsonify({
                'success': True,
                'location': location
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Drone not connected'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error: {str(e)}'
        })

@app.route('/select-mission')
def select_mission():
    """Manually trigger mission selection"""
    try:
        mission = select_best_mission()
        if mission:
            return jsonify({
                'success': True,
                'mission': mission,
                'message': 'Mission selected successfully'
            })
        else:
            return jsonify({
                'success': False,
                'message': 'No suitable mission available'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error selecting mission: {str(e)}'
        })

@app.route('/pending-requests')
def pending_requests():
    """Get all pending blood requests for debugging"""
    try:
        pending = BloodRequest.query.filter_by(status='pending').all()
        requests = []
        for req in pending:
            hospital = Hospital.query.get(req.hospital_id)
            requests.append({
                'id': req.id,
                'hospital': hospital.name,
                'blood_type': req.blood_type,
                'units': req.units,
                'urgency': req.urgency,
                'created_at': req.created_at.isoformat()
            })
        
        return jsonify({
            'success': True,
            'requests': requests,
            'count': len(requests)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Error getting requests: {str(e)}'
        })

@app.route('/fly-mission')
def fly_mission():
    try:
        # Check if already connected
        if not drone.is_connected:
            if not drone.connect():
                return jsonify({
                    'success': False,
                    'message': 'Failed to connect to drone'
                })
        
        # Get current location
        current_location = drone.get_location()
        if not current_location:
            return jsonify({
                'success': False,
                'message': 'No GPS data available'
            })
        
        # Set target location (Beijing coordinates)
        target_lat, target_lon = 39.9042, 116.4074
        
        # Log the mission
        logging.info(f"Starting mission from {current_location} to {target_lat}, {target_lon}")
        
        # For safety, we'll just simulate the mission for now
        # In a real scenario, you would call:
        # drone.arm_and_takeoff(10)
        # drone.goto_location(target_lat, target_lon, 10)
        # drone.return_to_launch()
        
        return jsonify({
            'success': True,
            'message': 'Mission completed!',
            'current_location': current_location,
            'target_location': {'lat': target_lat, 'lon': target_lon},
            'note': 'Mission simulated for safety - drone commands not executed'
        })
        
    except Exception as e:
        logging.error(f"Mission error: {e}")
        return jsonify({
            'success': False,
            'message': f'Mission error: {str(e)}'
        })

@app.route('/manage-hospitals', methods=['GET'])
def manage_hospitals():
    hospitals = Hospital.query.all()
    return render_template('manage_hospitals.html', hospitals=hospitals)

@app.route('/add-hospital', methods=['POST'])
def add_hospital():
    name = request.form.get('name')
    latitude = float(request.form.get('latitude'))
    longitude = float(request.form.get('longitude'))
    hospital = Hospital(name=name, latitude=latitude, longitude=longitude)
    db.session.add(hospital)
    db.session.commit()
    flash('Hospital added successfully!', 'success')
    return redirect(url_for('manage_hospitals'))

@app.route('/edit-hospital/<int:hospital_id>', methods=['POST'])
def edit_hospital(hospital_id):
    hospital = Hospital.query.get_or_404(hospital_id)
    hospital.name = request.form.get('name')
    hospital.latitude = float(request.form.get('latitude'))
    hospital.longitude = float(request.form.get('longitude'))
    db.session.commit()
    flash('Hospital updated successfully!', 'success')
    return redirect(url_for('manage_hospitals'))

@app.route('/delete-hospital/<int:hospital_id>')
def delete_hospital(hospital_id):
    hospital = Hospital.query.get_or_404(hospital_id)
    db.session.delete(hospital)
    db.session.commit()
    flash('Hospital deleted successfully!', 'success')
    return redirect(url_for('manage_hospitals'))

def emit_mission_queue_update():
    """Emit the latest mission queue to all connected clients"""
    pending_requests = BloodRequest.query.filter_by(status='pending').all()
    missions = []
    for req in pending_requests:
        from_hospital = Hospital.query.get(req.hospital_id)
        available_hospitals = Hospital.query.join(BloodInventory).filter(
            BloodInventory.blood_type == req.blood_type,
            BloodInventory.units >= req.units
        ).all()
        if available_hospitals:
            source_hospital = min(
                available_hospitals,
                key=lambda h: abs(h.latitude - from_hospital.latitude) + abs(h.longitude - from_hospital.longitude)
            )
        else:
            source_hospital = None
        urgency_map = {'critical': 0, 'urgent': 10, 'normal': 20}
        urgency_score = urgency_map.get(req.urgency, 30)
        time_waiting = (datetime.utcnow() - req.created_at).total_seconds() / 3600
        time_score = time_waiting * 5
        distance_score = 0
        if source_hospital:
            distance_score = geodesic((source_hospital.latitude, source_hospital.longitude), (from_hospital.latitude, from_hospital.longitude)).km * 2
        total_score = urgency_score + time_score + distance_score
        missions.append({
            'blood_type': req.blood_type,
            'units': req.units,
            'urgency': req.urgency,
            'from_hospital': {'name': source_hospital.name} if source_hospital else {'name': 'N/A'},
            'to_hospital': {'name': from_hospital.name} if from_hospital else {'name': 'N/A'},
            'status': req.status.capitalize(),
            'priority_score': round(total_score, 1)
        })
    missions.sort(key=lambda m: m['priority_score'])
    socketio.emit('mission_queue_update', {'missions': missions})

def process_blood_request(request_obj):
    requesting_hospital = Hospital.query.get(request_obj.hospital_id)
    available_hospitals = Hospital.query.join(BloodInventory).filter(
        BloodInventory.blood_type == request_obj.blood_type,
        BloodInventory.units >= request_obj.units
    ).all()

    if not available_hospitals:
        logging.warning(f"No hospitals found with required blood type {request_obj.blood_type}")
        emit_mission_queue_update()  # Update queue for all clients
        return

    nearest_hospital = min(
        available_hospitals,
        key=lambda h: geodesic(
            (requesting_hospital.latitude, requesting_hospital.longitude),
            (h.latitude, h.longitude)
        ).kilometers
    )

    logging.info(f"Route planned: From {nearest_hospital.name} to {requesting_hospital.name}")
    logging.info(f"Blood type: {request_obj.blood_type}, Units: {request_obj.units}")

    # Do NOT set status to 'scheduled' here; leave as 'pending' so it appears in the mission queue
    db.session.commit()
    emit_mission_queue_update()  # Update queue for all clients

def auto_start_mission():
    """Automatically start the highest priority pending mission if drone is available"""
    mission = select_best_mission()
    if mission:
        req = BloodRequest.query.get(mission['id'])
        # Error handling: prevent source == destination
        if mission['from_hospital']['name'] == mission['to_hospital']['name']:
            logging.error(f"Invalid mission: source and destination hospital are the same ({mission['from_hospital']['name']})")
            req.status = 'error'
            db.session.commit()
            emit_mission_queue_update()
            return
        # Safety check before sending commands
        src = mission['from_hospital']
        dest = mission['to_hospital']
        drone_status = get_drone_status()
        mission_params = {
            'battery_level': drone_status['battery_level'],
            'wind_speed': 0,  # Add real wind speed if available
            'visibility': 10000,  # Add real visibility if available
            'start_location': (src['lat'], src['lon']),
            'destination': (dest['lat'], dest['lon']),
            'planned_altitude': 20
        }
        if not safety_monitor.is_mission_safe(mission_params):
            logging.error(f"Mission failed safety check: {mission_params}")
            req.status = 'error'
            db.session.commit()
            emit_mission_queue_update()
            return
        if req.status == 'pending':
            req.status = 'scheduled'  # Mark as started
            db.session.commit()
            emit_mission_queue_update()
            logging.info(f"Mission auto-started: Request ID {req.id}, Status set to scheduled.")
            # Send MAVLink commands to Pixhawk
            try:
                drone.arm_and_takeoff(target_altitude=20)
                drone.goto_location(lat=src['lat'], lon=src['lon'], alt=20)
                drone.goto_location(lat=dest['lat'], lon=dest['lon'], alt=20)
                drone.return_to_launch()
                logging.info(f"Mission commands sent to Pixhawk: Takeoff, fly to {src['name']}, deliver to {dest['name']}, return to launch.")
            except Exception as e:
                logging.error(f"Error sending MAVLink commands: {e}")

# WebSocket events
@socketio.on('connect')
def handle_connect():
    # Automatically try to connect to the drone when page loads
    try:
        if drone.connect():
            location = drone.get_location()
            mission = get_current_mission()
            
            if location:
                emit('drone_status', {
                    'connected': True,
                    'mode': 'Connected',
                    'location': location,
                    'mission': mission,
                    'message': 'Drone connected successfully'
                })
            else:
                emit('drone_status', {
                    'connected': True,
                    'mode': 'Connected (No GPS)',
                    'location': None,
                    'mission': mission,
                    'message': 'Drone connected but no GPS data'
                })
        else:
            emit('drone_status', {
                'connected': False,
                'mode': 'Not Connected',
                'location': None,
                'mission': None,
                'message': 'Failed to connect to drone'
            })
    except Exception as e:
        emit('drone_status', {
            'connected': False,
            'mode': 'Error',
            'location': None,
            'mission': None,
            'message': f'Connection error: {str(e)}'
        })

@socketio.on('request_drone_status')
def handle_drone_status_request():
    # Return current drone status
    try:
        if drone.is_connected:
            location = drone.get_location()
            speed = drone.get_speed()
            battery = drone.get_battery_level()
            
            # Get comprehensive drone status
            drone_status = get_drone_status()
            
            # Get mission information
            mission = get_current_mission()
            
            # Only consider moving if speed > 0.5 m/s (to avoid GPS noise)
            is_moving = speed > 0.5
            
            # Create status message based on drone state
            if drone_status['is_charging']:
                status_message = f"Drone charging (Battery: {battery}%)"
            elif not drone_status['is_available']:
                status_message = f"Drone unavailable (Battery: {battery}%)"
            elif mission:
                status_message = f"Mission assigned: {mission['blood_type']} blood to {mission['to_hospital']['name']}"
            else:
                status_message = "Drone ready for missions"
            
            if location:
                emit('drone_status', {
                    'connected': True,
                    'mode': 'Connected',
                    'location': location,
                    'speed': speed,
                    'battery': battery,
                    'is_charging': drone_status['is_charging'],
                    'is_available': drone_status['is_available'],
                    'mission': mission,
                    'is_moving': is_moving,
                    'message': status_message
                })
            else:
                emit('drone_status', {
                    'connected': True,
                    'mode': 'Connected (No GPS)',
                    'location': None,
                    'speed': 0.0,
                    'battery': battery,
                    'is_charging': drone_status['is_charging'],
                    'is_available': drone_status['is_available'],
                    'mission': mission,
                    'is_moving': False,
                    'message': status_message
                })
        else:
            emit('drone_status', {
                'connected': False,
                'mode': 'Not Connected',
                'location': None,
                'speed': 0.0,
                'battery': 0,
                'is_charging': False,
                'is_available': False,
                'mission': None,
                'is_moving': False,
                'message': 'Drone not connected'
            })
    except Exception as e:
        emit('drone_status', {
            'connected': False,
            'mode': 'Error',
            'location': None,
            'speed': 0.0,
            'battery': 0,
            'is_charging': False,
            'is_available': False,
            'mission': None,
            'is_moving': False,
            'message': f'Status error: {str(e)}'
        })

LOG_PATH = 'drone_operations.log'

@app.route('/drone_log')
def drone_log():
    """Return recent user-friendly drone log entries as JSON"""
    try:
        if not os.path.exists(LOG_PATH):
            return jsonify({'logs': []})
        with open(LOG_PATH, 'r') as f:
            lines = f.readlines()[-300:]  # last 300 lines for more context
        # Only keep lines with a date and a clear English message, skip HTTP and technical lines
        user_logs = []
        for line in reversed(lines):
            # Skip HTTP request logs and technical errors
            if re.search(r'"GET|POST|socket.io|HTTP/1.1"', line):
                continue
            if re.search(r'(ERROR|WARNING|Exception|Traceback)', line):
                continue
            # Only keep lines with a date and a readable message
            if re.search(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}', line) and re.search(r'(Mission|Delivered|Takeoff|Connected|Disconnected|Battery|Arrived|Completed|Started|Returning|Armed|Ready|Blood request|Route planned|Units|Drone|No-fly zone)', line, re.IGNORECASE):
                # Remove log level and IP if present
                clean = re.sub(r' - (INFO|DEBUG|WARNING|ERROR) - .*? - ', ' - ', line)
                user_logs.append(clean.strip())
            if len(user_logs) >= 20:
                break
        return jsonify({'logs': list(reversed(user_logs))})
    except Exception as e:
        return jsonify({'logs': [f'Error reading log: {e}']})

@app.route('/mission-queue')
def mission_queue():
    """Return all pending missions, ranked by priority and urgency"""
    pending_requests = BloodRequest.query.filter_by(status='pending').all()
    missions = []
    for req in pending_requests:
        from_hospital = Hospital.query.get(req.hospital_id)
        available_hospitals = Hospital.query.join(BloodInventory).filter(
            BloodInventory.blood_type == req.blood_type,
            BloodInventory.units >= req.units
        ).all()
        if available_hospitals:
            source_hospital = min(
                available_hospitals,
                key=lambda h: abs(h.latitude - from_hospital.latitude) + abs(h.longitude - from_hospital.longitude)
            )
        else:
            source_hospital = None
        urgency_map = {'critical': 0, 'urgent': 10, 'normal': 20}
        urgency_score = urgency_map.get(req.urgency, 30)
        time_waiting = (datetime.utcnow() - req.created_at).total_seconds() / 3600  # hours
        time_score = time_waiting * 5
        distance_score = 0
        if source_hospital:
            distance_score = geodesic((source_hospital.latitude, source_hospital.longitude), (from_hospital.latitude, from_hospital.longitude)).km * 2
        total_score = urgency_score + time_score + distance_score
        missions.append({
            'blood_type': req.blood_type,
            'units': req.units,
            'urgency': req.urgency,
            'from_hospital': {'name': source_hospital.name} if source_hospital else {'name': 'N/A'},
            'to_hospital': {'name': from_hospital.name} if from_hospital else {'name': 'N/A'},
            'status': req.status.capitalize(),
            'priority_score': round(total_score, 1)
        })
    missions.sort(key=lambda m: m['priority_score'])
    return jsonify({'missions': missions})

if __name__ == '__main__':
    # Prevent double initialization
    import sys
    if hasattr(sys, '_called_main') and sys._called_main:
        print("Application already initialized, skipping...")
        sys.exit(0)
    
    sys._called_main = True
    
    print("Creating database tables...")
    with app.app_context():
        db.create_all()
    
    print("Starting Flask application...")
    print("The application will be available at http://localhost:5000")
    socketio.run(app, debug=False, host='0.0.0.0', port=5000)