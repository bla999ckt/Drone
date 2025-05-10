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

# Configure logging
logging.basicConfig(
    filename='drone_operations.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

print("Starting application initialization...")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blood_inventory.db'
db = SQLAlchemy(app)
socketio = SocketIO(app, async_mode='gevent')

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

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/request-blood', methods=['GET', 'POST'])
def request_blood():
    if request.method == 'POST':
        hospital_id = request.form.get('hospital_id')
        blood_type = request.form.get('blood_type')
        units = int(request.form.get('units'))
        urgency = request.form.get('urgency')

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
        
        # Find nearest hospital with required blood
        process_blood_request(request_obj)
        
        flash('Blood request submitted successfully!', 'success')
        return redirect(url_for('index'))
    
    hospitals = Hospital.query.all()
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
    emit('drone_status', {'status': 'disconnected', 'message': 'Drone system not yet implemented'})

@socketio.on('request_drone_status')
def handle_drone_status_request():
    emit('drone_status', {'status': 'disconnected', 'message': 'Drone system not yet implemented'})

if __name__ == '__main__':
    print("Creating database tables...")
    with app.app_context():
        db.create_all()
    
    print("Starting Flask application...")
    print("The application will be available at http://localhost:5000")
    socketio.run(app, debug=True, host='0.0.0.0', port=5000) 