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

# Import drone controller
from drone_controller import DroneController

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

# Only print initialization message once
if not hasattr(app, '_initialized'):
    print("Starting application initialization...")
    app._initialized = True

# Initialize drone controller with the correct port
# Use the working port we discovered
drone = DroneController(connection_string='/dev/tty.usbmodem14203')

print("Flask app and SocketIO initialized...")

# Database Models
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
    if request.method == 'POST':
        blood_type = request.form.get('blood_type')
        units = int(request.form.get('units'))
        urgency = request.form.get('urgency')

        # Automatically assign to the first available hospital
        # In a real implementation, this would be based on user authentication or location
        default_hospital = Hospital.query.first()
        if not default_hospital:
            flash('No hospitals available in the system', 'error')
            return redirect(url_for('request_blood'))

        request_obj = BloodRequest(
            hospital_id=default_hospital.id,
            blood_type=blood_type,
            units=units,
            urgency=urgency
        )
        db.session.add(request_obj)
        db.session.commit()

        # Log the request
        logging.info(f"New blood request: Hospital {default_hospital.name}, Blood Type {blood_type}, Units {units}, Urgency {urgency}")
        
        # Find nearest hospital with required blood
        process_blood_request(request_obj)
        
        flash('Blood request submitted successfully!', 'success')
        return redirect(url_for('index'))
    
    return render_template('request_blood.html')

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
def drone_status():
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

def process_blood_request(request_obj):
    requesting_hospital = Hospital.query.get(request_obj.hospital_id)
    available_hospitals = Hospital.query.join(BloodInventory).filter(
        BloodInventory.blood_type == request_obj.blood_type,
        BloodInventory.units >= request_obj.units
    ).all()

    if not available_hospitals:
        logging.warning(f"No hospitals found with required blood type {request_obj.blood_type}")
        return

    # Find nearest hospital with required blood
    nearest_hospital = min(
        available_hospitals,
        key=lambda h: geodesic(
            (requesting_hospital.latitude, requesting_hospital.longitude),
            (h.latitude, h.longitude)
        ).kilometers
    )

    logging.info(f"Route planned: From {nearest_hospital.name} to {requesting_hospital.name}")
    logging.info(f"Blood type: {request_obj.blood_type}, Units: {request_obj.units}")

    # Update request status
    request_obj.status = 'scheduled'
    db.session.commit()

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