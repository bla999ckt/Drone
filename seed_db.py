from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

# Create Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'key'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///blood_inventory.db'
db = SQLAlchemy(app)

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

# Sample data
sample_hospitals = [
    {"name": "Central Hospital", "latitude": 40.7128, "longitude": -74.0060},
    {"name": "Northside Clinic", "latitude": 40.7306, "longitude": -73.9352},
    {"name": "East Medical Center", "latitude": 40.6500, "longitude": -73.9496},
    {"name": "West Health Center", "latitude": 40.7306, "longitude": -74.0018},
    {"name": "South General", "latitude": 40.7000, "longitude": -73.9000},
]

sample_inventory = [
    {"blood_type": "A+", "units": 10},
    {"blood_type": "A-", "units": 5},
    {"blood_type": "B+", "units": 8},
    {"blood_type": "O+", "units": 12},
    {"blood_type": "AB-", "units": 2},
]

def seed():
    with app.app_context():
        # Drop all existing tables and create new ones
        db.drop_all()
        db.create_all()
        
        # Add hospitals
        for hosp in sample_hospitals:
            hospital = Hospital(name=hosp["name"], latitude=hosp["latitude"], longitude=hosp["longitude"])
            db.session.add(hospital)
            db.session.flush()  # Get hospital.id
            
            # Add inventory for each hospital
            for inv in sample_inventory:
                db.session.add(BloodInventory(
                    hospital_id=hospital.id,
                    blood_type=inv["blood_type"],
                    units=inv["units"]
                ))
        
        # Commit all changes
        db.session.commit()
        print("Database seeded with sample hospitals and blood inventory.")

if __name__ == "__main__":
    seed() 