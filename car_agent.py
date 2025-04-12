import datetime
import random
import uuid
from flask import Flask, request, jsonify

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Agent Configuration ---
AGENT_PORT = 5003 # Run this agent on port 5003
AGENT_BASE_URL = f"http://127.0.0.1:{AGENT_PORT}"

# --- Agent Card Definition ---
AGENT_CARD = {
    "agentId": "car-rental-004",
    "displayName": "RoadRunner Car Rentals",
    "description": "Searches for and books rental cars.",
    "endpointUrl": AGENT_BASE_URL,
    "capabilities": [
        {
          "capabilityId": "searchCars",
          "description": "Finds available rental cars.",
        },
        {
          "capabilityId": "bookCar",
          "description": "Books a specific rental car identified by carId.",
        }
    ],
    "definitions": {
        "carOption": {
          "type": "object",
          "properties": {
            "carId": { "type": "string" },
            "make": { "type": "string" },
            "model": { "type": "string" },
            "type": { "type": "string" },
            "location": { "type": "string" },
            "pricePerDay": { "type": "number", "format": "float" },
            "currency": { "type": "string" }
          }
        },
        "bookingConfirmation": {
          "type": "object",
          "properties": {
            "bookingId": { "type": "string" },
            "status": { "type": "string", "enum": ["Confirmed", "Pending", "Failed"] },
            "message": { "type": "string", "nullable": True }
          }
        }
      }
}

# --- Mock Data ---
MOCK_CAR_MAKES_MODELS = {
    "Toyota": ["Vios", "Camry", "Altis", "RAV4"],
    "Honda": ["Civic", "City", "HR-V", "CR-V"],
    "BMW": ["3 Series", "5 Series", "X1"],
    "Mercedes-Benz": ["C-Class", "E-Class", "GLA"],
    "Hyundai": ["Avante", "Tucson"]
}
MOCK_CAR_TYPES = ["Sedan", "SUV", "Compact", "Luxury"]

# --- Helper Functions ---
def generate_mock_cars(location, car_type_query):
    """Generates a list of mock car rental options."""
    cars = []
    num_cars = random.randint(1, 5)

    for i in range(num_cars):
        make = random.choice(list(MOCK_CAR_MAKES_MODELS.keys()))
        model = random.choice(MOCK_CAR_MAKES_MODELS[make])
        car_id = f"CAR-{make[:3].upper()}-{random.randint(100, 999)}"
        
        # Assign a type, try to match query if provided
        assigned_type = random.choice(MOCK_CAR_TYPES)
        if car_type_query:
            # Simple matching for mock
            for t in MOCK_CAR_TYPES:
                 if t.lower() in car_type_query.lower():
                      assigned_type = t
                      break
        
        price_per_day = round(random.uniform(50.0, 250.0), 2)
        if assigned_type == "Luxury": price_per_day *= 1.5
        if assigned_type == "SUV": price_per_day *= 1.2


        cars.append({
            "carId": car_id,
            "make": make,
            "model": model,
            "type": assigned_type,
            "location": location, # Assume cars are available at the requested pickup location
            "pricePerDay": round(price_per_day, 2),
            "currency": "SGD"
        })
        
    # Filter if a specific type was requested and found
    if car_type_query:
        filtered_cars = [c for c in cars if c['type'].lower() in car_type_query.lower()]
        if filtered_cars: # Return only matching types if any were found
             return filtered_cars
             
    return cars


# --- API Endpoints ---

@app.route('/agent-card', methods=['GET'])
def get_agent_card():
    """Endpoint to return the agent's card."""
    return jsonify(AGENT_CARD)

@app.route('/searchCars', methods=['POST'])
def search_cars():
    """Endpoint to search for mock rental cars."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    location = data.get('location')
    pickup_date = data.get('pickupDate') # Not used in mock logic
    dropoff_date = data.get('dropoffDate') # Not used in mock logic
    car_type = data.get('carType') # Optional

    if not all([location, pickup_date, dropoff_date]):
        return jsonify({"error": "Missing required parameters: location, pickupDate, dropoffDate"}), 400

    print(f"[CarAgent] Received car search: Location='{location}', Type='{car_type}', Dates={pickup_date}-{dropoff_date}")

    # Generate mock results
    mock_cars = generate_mock_cars(location, car_type)

    print(f"[CarAgent] Returning {len(mock_cars)} mock cars.")
    return jsonify({"cars": mock_cars})

@app.route('/bookCar', methods=['POST'])
def book_car():
    """Endpoint to 'book' a mock car."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    car_id = data.get('carId')
    driver_details = data.get('driverDetails') # Not used in mock

    if not car_id or not driver_details:
        return jsonify({"error": "Missing required parameters: carId, driverDetails"}), 400

    print(f"[CarAgent] Received booking request for car: {car_id}")

    # Simulate booking success
    booking_id = f"REN-{uuid.uuid4()}"
    status = "Confirmed"
    message = f"Car {car_id} booked successfully."

    print(f"[CarAgent] Mock booking successful: {booking_id}")
    return jsonify({
        "bookingId": booking_id,
        "status": status,
        "message": message
    })

# --- Main Execution ---
if __name__ == '__main__':
    print(f"--- Car Rental Agent ---")
    print(f"Running on {AGENT_BASE_URL}")
    print(f"Access Agent Card at: {AGENT_BASE_URL}/agent-card")
    app.run(port=AGENT_PORT, debug=False)

