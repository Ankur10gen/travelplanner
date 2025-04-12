import datetime
import random
import uuid
from flask import Flask, request, jsonify

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Agent Configuration ---
AGENT_PORT = 5001 # Run this agent on port 5001
AGENT_BASE_URL = f"http://127.0.0.1:{AGENT_PORT}"

# --- Agent Card Definition ---
# This data structure represents the agent's capabilities for discovery.
AGENT_CARD = {
    "agentId": "flight-booker-002",
    "displayName": "SkyHigh Flight Booker",
    "description": "Searches for and books airline tickets.",
    "endpointUrl": AGENT_BASE_URL,
    "capabilities": [
        {
          "capabilityId": "searchFlights",
          "description": "Finds available flights based on criteria.",
          # Parameters and response schema are implicitly defined by the endpoint logic below
          # In a real system, these might be more formally defined (e.g., using JSON Schema)
        },
        {
          "capabilityId": "bookFlight",
          "description": "Books a specific flight identified by flightId.",
        }
    ],
    # In a richer implementation, detailed parameter/response schemas might be included here.
    "definitions": {
        "flightOption": {
          "type": "object",
          "properties": {
            "flightId": { "type": "string" },
            "airline": { "type": "string" },
            "origin": { "type": "string" },
            "destination": { "type": "string" },
            "departureTime": { "type": "string", "format": "date-time" },
            "arrivalTime": { "type": "string", "format": "date-time" },
            "price": { "type": "number", "format": "float" },
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
MOCK_AIRLINES = ["SG Air", "Lion Fly", "Asia Budget", "Sky Connect"]

# --- Helper Functions ---
def generate_mock_flights(origin, destination, departure_date_str, passengers):
    """Generates a list of mock flight options."""
    flights = []
    try:
        departure_date = datetime.datetime.strptime(departure_date_str, "%Y-%m-%d").date()
    except ValueError:
        # Handle invalid date format if necessary, here we'll just use today
        departure_date = datetime.date.today()

    for i in range(random.randint(1, 5)): # Generate 1 to 5 mock flights
        airline = random.choice(MOCK_AIRLINES)
        flight_id = f"{airline.replace(' ', '')[:3].upper()}-{random.randint(100, 999)}"
        
        dep_hour = random.randint(6, 22)
        dep_minute = random.choice([0, 15, 30, 45])
        departure_time = datetime.datetime.combine(departure_date, datetime.time(dep_hour, dep_minute))
        
        flight_duration_hours = random.uniform(1.5, 12.0) # Example duration
        arrival_time = departure_time + datetime.timedelta(hours=flight_duration_hours)

        price = round(random.uniform(150.0, 1200.0) * passengers, 2) # Price scales with passengers

        flights.append({
            "flightId": flight_id,
            "airline": airline,
            "origin": origin,
            "destination": destination,
            "departureTime": departure_time.isoformat() + "Z", # ISO 8601 format
            "arrivalTime": arrival_time.isoformat() + "Z",
            "price": price,
            "currency": "SGD" # Assuming Singapore Dollar based on location context
        })
    return flights

# --- API Endpoints ---

@app.route('/agent-card', methods=['GET'])
def get_agent_card():
    """Endpoint to return the agent's card."""
    return jsonify(AGENT_CARD)

@app.route('/searchFlights', methods=['POST'])
def search_flights():
    """Endpoint to search for mock flights."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    origin = data.get('origin')
    destination = data.get('destination')
    departure_date = data.get('departureDate')
    passengers = data.get('passengers')

    # Basic validation
    if not all([origin, destination, departure_date, passengers]):
        return jsonify({"error": "Missing required parameters: origin, destination, departureDate, passengers"}), 400
    
    try:
        passengers = int(passengers)
        if passengers < 1:
             raise ValueError("Passengers must be at least 1")
    except (ValueError, TypeError):
         return jsonify({"error": "Invalid value for passengers"}), 400


    print(f"[FlightAgent] Received flight search: {origin} -> {destination} on {departure_date} for {passengers}")

    # Generate mock results
    mock_flights = generate_mock_flights(origin, destination, departure_date, passengers)

    print(f"[FlightAgent] Returning {len(mock_flights)} mock flights.")
    return jsonify({"flights": mock_flights})

@app.route('/bookFlight', methods=['POST'])
def book_flight():
    """Endpoint to 'book' a mock flight."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    flight_id = data.get('flightId')
    passenger_details = data.get('passengerDetails') # We don't actually use this in the mock

    if not flight_id or not passenger_details:
        return jsonify({"error": "Missing required parameters: flightId, passengerDetails"}), 400

    print(f"[FlightAgent] Received booking request for flight: {flight_id}")

    # Simulate booking success
    booking_id = f"FLT-{uuid.uuid4()}"
    status = "Confirmed"
    message = f"Flight {flight_id} booked successfully."

    print(f"[FlightAgent] Mock booking successful: {booking_id}")
    return jsonify({
        "bookingId": booking_id,
        "status": status,
        "message": message
    })

# --- Main Execution ---
if __name__ == '__main__':
    print(f"--- Flight Booker Agent ---")
    print(f"Running on {AGENT_BASE_URL}")
    print(f"Access Agent Card at: {AGENT_BASE_URL}/agent-card")
    app.run(port=AGENT_PORT, debug=False) # Turn debug=True for development details

