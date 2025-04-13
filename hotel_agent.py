import datetime
import random
import uuid
from flask import Flask, request, jsonify

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Agent Configuration ---
AGENT_PORT = 5002 # Run this agent on port 5002
AGENT_BASE_URL = f"http://127.0.0.1:{AGENT_PORT}"

# --- Agent Card Definition ---
AGENT_CARD = {
    "agentId": "hotel-booker-003",
    "displayName": "CozyStays Hotel Reservations",
    "description": "Searches for and books hotel rooms.",
    "endpointUrl": AGENT_BASE_URL,
    "capabilities": [
        {
          "capabilityId": "searchHotels",
          "description": "Finds available hotels based on criteria.",
          "path": "/searchHotels" # <<< ADDED
        },
        {
          "capabilityId": "bookHotel",
          "description": "Books a specific hotel room identified by hotelId.",
          "path": "/bookHotel" # <<< ADDED
        }
    ],
     "definitions": {
        "hotelOption": {
          "type": "object",
          "properties": {
            "hotelId": { "type": "string" },
            "name": { "type": "string" },
            "location": { "type": "string" },
            "rating": { "type": "number", "format": "float", "minimum": 1, "maximum": 5 },
            "pricePerNight": { "type": "number", "format": "float" },
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
MOCK_HOTEL_NAMES = ["Grand Plaza", "Marina Bay Sands View", "Orchard Retreat", "Sentosa Getaway", "City Center Inn", "Riverside Hotel"]
MOCK_LOCATIONS = ["Downtown", "Marina Bay", "Orchard Road", "Sentosa", "Chinatown", "Clarke Quay"]

# --- Helper Functions ---
def generate_mock_hotels(location_query, guests):
    """Generates a list of mock hotel options."""
    hotels = []
    # Simple simulation: return hotels in a related mock location or just random ones
    relevant_location = location_query or random.choice(MOCK_LOCATIONS) # Use query or random if missing

    # Ensure guests is valid
    try:
        num_guests = int(guests or 1)
        if num_guests < 1: num_guests = 1
    except (ValueError, TypeError):
        num_guests = 1

    num_hotels = random.randint(1, 4)

    for i in range(num_hotels):
        hotel_name = random.choice(MOCK_HOTEL_NAMES)
        hotel_id = f"HTL-{random.randint(1000, 9999)}"
        rating = round(random.uniform(3.5, 5.0), 1)
        price_per_night = round(random.uniform(120.0, 600.0) * (1 + (num_guests -1) * 0.2) , 2) # Price adjusts slightly for guests
        loc = random.choice(MOCK_LOCATIONS) # Keep it simple for mock

        hotels.append({
            "hotelId": hotel_id,
            "name": hotel_name,
            "location": loc,
            "rating": rating,
            "pricePerNight": price_per_night,
            "currency": "SGD"
        })
    return hotels

# --- API Endpoints ---

@app.route('/agent-card', methods=['GET'])
def get_agent_card():
    """Endpoint to return the agent's card."""
    return jsonify(AGENT_CARD)

@app.route('/searchHotels', methods=['POST'])
def search_hotels():
    """Endpoint to search for mock hotels."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    location = data.get('location')
    check_in_date = data.get('checkInDate')
    check_out_date = data.get('checkOutDate')
    guests = data.get('guests')

    if not all([location, check_in_date, check_out_date]):
        # Guests defaults to 1 in helper
        return jsonify({"error": "Missing required parameters: location, checkInDate, checkOutDate"}), 400

    print(f"[HotelAgent] Received hotel search: Location='{location}', Guests={guests or 1}, Dates={check_in_date}-{check_out_date}")

    # Generate mock results
    mock_hotels = generate_mock_hotels(location, guests)

    print(f"[HotelAgent] Returning {len(mock_hotels)} mock hotels.")
    return jsonify({"hotels": mock_hotels})

@app.route('/bookHotel', methods=['POST'])
def book_hotel():
    """Endpoint to 'book' a mock hotel."""
    data = request.get_json()
    if not data:
        return jsonify({"error": "Invalid JSON payload"}), 400

    hotel_id = data.get('hotelId')
    guest_details = data.get('guestDetails')

    if not hotel_id or not guest_details:
        return jsonify({"error": "Missing required parameters: hotelId, guestDetails"}), 400

    print(f"[HotelAgent] Received booking request for hotel: {hotel_id}")

    # Simulate booking success
    booking_id = f"HOT-{uuid.uuid4()}"
    status = "Confirmed"
    message = f"Hotel {hotel_id} booked successfully."

    print(f"[HotelAgent] Mock booking successful: {booking_id}")
    return jsonify({
        "bookingId": booking_id,
        "status": status,
        "message": message
    })

# --- Main Execution ---
if __name__ == '__main__':
    print(f"--- Hotel Booker Agent ---")
    print(f"Running on {AGENT_BASE_URL}")
    print(f"Access Agent Card at: {AGENT_BASE_URL}/agent-card")
    app.run(port=AGENT_PORT, debug=False)

