# Blood Delivery Drone System

A Flask-based web application for managing blood inventory and delivery between hospitals using drones.

## Current Features

- Hospital management system
- Blood inventory tracking
- Blood request management
- Real-time status updates
- Interactive map interface

## Setup Instructions

1. **Create and activate virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Initialize the database**:
   ```bash
   python seed_db.py
   ```

4. **Run the application**:
   ```bash
   python app.py
   ```

The application will be available at `http://localhost:5000`

## Project Structure

- `app.py`: Main Flask application
- `seed_db.py`: Database initialization script
- `templates/`: HTML templates
- `static/`: Static files (CSS, JS, images)
- `blood_inventory.db`: SQLite database file

## Database Schema

### Hospitals
- id (Primary Key)
- name
- latitude
- longitude

### Blood Inventory
- id (Primary Key)
- hospital_id (Foreign Key)
- blood_type
- units
- last_updated

## Development Status

### Current Phase
- Basic web interface
- Hospital management
- Blood inventory tracking
- Sample data seeding

### Next Steps
- Drone integration
- Real-time tracking
- Automated delivery scheduling
- Weather monitoring
- Safety protocols

## Notes

- The current version uses a demo database with sample hospitals and blood inventory
- Hospitals can update their inventory through the web interface
- The drone integration is planned for future development


