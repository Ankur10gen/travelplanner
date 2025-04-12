import datetime
import re
import requests # Library to make HTTP requests
import uuid # Needed for mock passenger/driver details generation
from flask import Flask, request, jsonify

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Agent Configuration ---
AGENT_PORT = 5000 # Run this agent on port 5000
AGENT_BASE_URL = f"http://127.0.0.1:{AGENT_PORT}"

# --- Configuration for Specialist Agents ---
# These URLs point to where the other agents are running locally.
FLIGHT_AGENT_URL = "http://127.0.0.1:5001"
HOTEL_AGENT_URL = "http://127.0.0.1:5002"
CAR_AGENT_URL = "http://127.0.0.1:5003"

# --- Agent Card Definition ---
AGENT_CARD = {
    "agentId": "travel-planner-001",
    "displayName": "TripMaster AI Planner",
    "description": "Coordinates flight, hotel, and car rental bookings based on user travel requests.",
    "endpointUrl": AGENT_BASE_URL,
    "capabilities": [
        {
          "capabilityId": "planTrip",
          "description": "Takes a natural language travel request, understands the requirements (flights, hotels, cars, dates, locations, passengers), calls relevant specialist agents, and returns a proposed itinerary or booking confirmation.",
          # Parameters and response schema defined implicitly below
        }
    ]
}

# --- LLM Simulation & Helper Functions ---

def simulate_llm_parse_query(query):
    """
    ** MOCK FUNCTION **
    Simulates an LLM parsing the user query to extract intents and entities.
    In a real implementation, this would involve calling an actual LLM API.
    """
    print(f"[PlannerAgent] Simulating LLM parsing for query: '{query}'")
    intents = set()
    entities = {
        "origin": None,
        "destination": None,
        "departureDate": None,
        "returnDate": None, # Optional
        "checkInDate": None,
        "checkOutDate": None,
        "pickupDate": None, # Car rental pickup
        "dropoffDate": None, # Car rental dropoff
        "passengers": 1, # Default
        "guests": 1, # Default for hotel
        "location": None, # General location for hotel/car
        "hotel_location_preference": None, # e.g., "near Eiffel Tower"
        "carType": None # Optional
    }

    # Basic keyword spotting (very simplistic simulation)
    query_lower = query.lower()
    if "flight" in query_lower or "fly" in query_lower or "ticket" in query_lower:
        intents.add("searchFlights")
        intents.add("bookFlight") # Assume booking intent for simplicity in mock

    if "hotel" in query_lower or "stay" in query_lower or "accommodation" in query_lower:
        intents.add("searchHotels")
        intents.add("bookHotel") # Assume booking

    if "car" in query_lower or "rental" in query_lower or "drive" in query_lower:
        intents.add("searchCars")
        intents.add("bookCar") # Assume booking

    # --- Entity Extraction Simulation ---

    # Passengers/Guests (simple number extraction)
    match = re.search(r"(\d+)\s+(people|person|passengers|guests)", query_lower)
    if match:
        try:
            num = int(match.group(1))
            if num > 0:
                entities["passengers"] = num
                entities["guests"] = num # Assume same number for hotel guests
        except ValueError:
            pass # Ignore if number conversion fails

    # Dates (very basic "next week", "tomorrow", specific date simulation)
    today = datetime.date.today()
    dep_date = None
    ret_date = None # Initialize return date

    if "next week" in query_lower:
        # Calculate start of next week (Monday)
        days_until_monday = (7 - today.weekday()) % 7
        dep_date = today + datetime.timedelta(days=days_until_monday if days_until_monday > 0 else 7)
        ret_date = dep_date + datetime.timedelta(days=4) # Assume 5 nights/days (e.g., Mon-Fri)
    elif "tomorrow" in query_lower:
        dep_date = today + datetime.timedelta(days=1)
        ret_date = dep_date + datetime.timedelta(days=4) # Assume 5 nights/days
    else:
        # Look for YYYY-MM-DD - add more robust parsing if needed
        date_matches = re.findall(r"(\d{4}-\d{2}-\d{2})", query)
        if len(date_matches) >= 1:
            try:
                dep_date = datetime.datetime.strptime(date_matches[0], "%Y-%m-%d").date()
                # If a second date is found, assume it's the return date
                if len(date_matches) >= 2:
                     ret_date = datetime.datetime.strptime(date_matches[1], "%Y-%m-%d").date()
                     # Simple validation: ensure return date is after departure date
                     if ret_date <= dep_date:
                          ret_date = dep_date + datetime.timedelta(days=5) # Default duration if invalid range
                else:
                     # Default duration if only one date found
                     ret_date = dep_date + datetime.timedelta(days=5)
            except ValueError:
                 pass # Ignore invalid date formats

    # Assign dates if found, otherwise they remain None initially
    if dep_date:
        entities["departureDate"] = dep_date.strftime("%Y-%m-%d")
        entities["checkInDate"] = dep_date.strftime("%Y-%m-%d")
        entities["pickupDate"] = dep_date.strftime("%Y-%m-%d") + "T12:00:00Z" # Default time

    if ret_date:
        entities["returnDate"] = ret_date.strftime("%Y-%m-%d")
        entities["checkOutDate"] = ret_date.strftime("%Y-%m-%d")
        entities["dropoffDate"] = ret_date.strftime("%Y-%m-%d") + "T12:00:00Z" # Default time


    # Locations (simple 'from X to Y' or 'in Z' logic)
    # Prioritize 'from X to Y' structure
    match_from_to = re.search(r"from\s+([\w\s-]+)\s+to\s+([\w\s-]+)", query_lower)
    if match_from_to:
        entities["origin"] = match_from_to.group(1).strip().title()
        entities["destination"] = match_from_to.group(2).strip().title()
        entities["location"] = entities["destination"] # Assume hotel/car location is destination
    else:
        # Fallback: Look for 'in/to Z' if 'from X to Y' not found
        match_in = re.search(r"\b(in|to)\s+([\w\s-]+)", query_lower)
        if match_in:
             loc = match_in.group(2).strip().title()
             # If flight intent exists but origin wasn't found via 'from X', set default origin
             if "searchFlights" in intents and not entities["origin"]:
                 entities["origin"] = "Singapore" # Default origin based on context
                 entities["destination"] = loc
             entities["location"] = loc # General location for hotel/car

    # Hotel Preference (e.g., "near X")
    match_near = re.search(r"near\s+([\w\s-]+)", query_lower)
    if match_near:
        pref = "Near " + match_near.group(1).strip().title()
        entities["hotel_location_preference"] = pref
        if not entities["location"]: # If only preference is given, use it as general location too
             entities["location"] = pref # Use preference as the main location

    # Car Type
    for car_t in ["compact", "sedan", "suv", "luxury", "convertible"]:
        if car_t in query_lower:
            entities["carType"] = car_t.title()
            break

    # --- Refine location if only hotel pref was found ---
    if entities["location"] and entities["location"].startswith("Near "):
         # Try to extract the core location name for broader searches if needed
         core_loc = entities["location"].replace("Near ", "")
         # In a real system you might use this core_loc for flight/car search
         # and the full preference for hotel search. For mock, we'll pass the pref.
         # entities["location"] = core_loc # Decide if you want to override general location
         pass # Keep location as "Near X" for now for hotel search consistency


    # --- Apply Defaults if necessary ---
    if "searchFlights" in intents:
        if not entities["origin"]: entities["origin"] = "Singapore" # Default origin
        if not entities["destination"]: entities["destination"] = "London" # Default destination
        if not entities["departureDate"]: # Default date if not parsed
             default_dep_date = datetime.date.today() + datetime.timedelta(days=7)
             entities["departureDate"] = default_dep_date.strftime("%Y-%m-%d")
             # Also set return date if departure was defaulted
             if not entities["returnDate"]:
                  entities["returnDate"] = (default_dep_date + datetime.timedelta(days=5)).strftime("%Y-%m-%d")

    if ("searchHotels" in intents or "searchCars" in intents) and not entities["location"]:
        entities["location"] = entities["destination"] if entities["destination"] else "London" # Default location

    # Ensure related dates are consistent if one set was defaulted/parsed
    if entities["departureDate"] and not entities["checkInDate"]:
        entities["checkInDate"] = entities["departureDate"]
        entities["pickupDate"] = entities["departureDate"] + "T12:00:00Z"
    if entities["returnDate"] and not entities["checkOutDate"]:
         entities["checkOutDate"] = entities["returnDate"]
         entities["dropoffDate"] = entities["returnDate"] + "T12:00:00Z"


    print(f"[PlannerAgent] Simulated Parse Results - Intents: {intents}, Entities: {entities}")
    return intents, entities

def call_agent_api(base_url, capability_path, payload):
    """Helper function to call another agent's API endpoint."""
    url = f"{base_url}/{capability_path}"
    headers = {'Content-Type': 'application/json'}
    try:
        print(f"[PlannerAgent] Calling {url} with payload: {payload}")
        response = requests.post(url, json=payload, headers=headers, timeout=10) # 10 second timeout
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
        print(f"[PlannerAgent] Received response from {url}: Status {response.status_code}")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[PlannerAgent] Error calling {url}: {e}")
        return {"error": f"Failed to call {base_url}: {e}"}
    except Exception as e:
        print(f"[PlannerAgent] Unexpected error during API call to {url}: {e}")
        return {"error": f"Unexpected error calling {base_url}: {e}"}


# --- API Endpoints ---

@app.route('/agent-card', methods=['GET'])
def get_agent_card():
    """Endpoint to return the agent's card."""
    return jsonify(AGENT_CARD)

@app.route('/planTrip', methods=['POST'])
def plan_trip():
    """Endpoint to plan a trip based on natural language query."""
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({"error": "Invalid JSON payload, 'query' field required"}), 400

    query = data['query']
    print(f"\n[PlannerAgent] Received planning request: '{query}'")

    # 1. Simulate LLM Parsing
    intents, entities = simulate_llm_parse_query(query)

    # 2. Prepare results structure
    results = {
        "status": "Processing",
        "summary": "",
        "details": {
            "flightBookingId": None,
            "hotelBookingId": None,
            "carRentalBookingId": None,
            "errors": []
        }
    }

    # 3. Call Specialist Agents based on Intents

    # --- Flight Handling ---
    if "searchFlights" in intents:
        flight_payload = {
            "origin": entities.get("origin"),
            "destination": entities.get("destination"),
            "departureDate": entities.get("departureDate"),
            "returnDate": entities.get("returnDate"), # Include if round trip implied/found
            "passengers": entities.get("passengers")
        }
        # **FIXED VALIDATION:** Check only required fields for searchFlights
        required_flight_fields = ["origin", "destination", "departureDate", "passengers"]
        missing_fields = [field for field in required_flight_fields if not flight_payload.get(field)]

        if missing_fields:
             error_msg = f"Missing required flight details: {', '.join(missing_fields)}."
             results["details"]["errors"].append(error_msg)
             print(f"[PlannerAgent] Validation Error: {error_msg}") # Add log
        else:
            search_response = call_agent_api(FLIGHT_AGENT_URL, "searchFlights", flight_payload)
            if "error" in search_response:
                results["details"]["errors"].append(f"Flight search failed: {search_response['error']}")
            elif search_response.get("flights"):
                # ** MOCK DECISION: Just pick the first flight found **
                first_flight = search_response["flights"][0]
                print(f"[PlannerAgent] Mock Decision: Selecting flight {first_flight.get('flightId')}")

                if "bookFlight" in intents:
                     # Prepare mock passenger details
                     mock_passengers = [{"name": f"Traveller {i+1}", "id": str(uuid.uuid4())} for i in range(entities.get("passengers", 1))]
                     booking_payload = {
                         "flightId": first_flight.get("flightId"),
                         "passengerDetails": mock_passengers
                     }
                     booking_response = call_agent_api(FLIGHT_AGENT_URL, "bookFlight", booking_payload)
                     if "error" in booking_response:
                          results["details"]["errors"].append(f"Flight booking failed: {booking_response['error']}")
                     elif booking_response.get("status") == "Confirmed":
                          results["details"]["flightBookingId"] = booking_response.get("bookingId")
                          print(f"[PlannerAgent] Flight booking confirmed: {results['details']['flightBookingId']}")
                     else:
                          results["details"]["errors"].append(f"Flight booking status: {booking_response.get('status', 'Unknown')}")
            else:
                 results["details"]["errors"].append("No flights found matching criteria.")


    # --- Hotel Handling ---
    if "searchHotels" in intents:
        hotel_payload = {
             # Prefer specific preference if available, else use general location
            "location": entities.get("hotel_location_preference") or entities.get("location"),
            "checkInDate": entities.get("checkInDate"),
            "checkOutDate": entities.get("checkOutDate"),
            "guests": entities.get("guests")
        }
        # Validation for hotel search
        required_hotel_fields = ["location", "checkInDate", "checkOutDate", "guests"]
        missing_hotel_fields = [field for field in required_hotel_fields if not hotel_payload.get(field)]

        if missing_hotel_fields:
             error_msg = f"Missing required hotel details: {', '.join(missing_hotel_fields)}."
             results["details"]["errors"].append(error_msg)
             print(f"[PlannerAgent] Validation Error: {error_msg}") # Add log
        else:
            search_response = call_agent_api(HOTEL_AGENT_URL, "searchHotels", hotel_payload)
            if "error" in search_response:
                results["details"]["errors"].append(f"Hotel search failed: {search_response['error']}")
            elif search_response.get("hotels"):
                 # ** MOCK DECISION: Just pick the first hotel found **
                first_hotel = search_response["hotels"][0]
                print(f"[PlannerAgent] Mock Decision: Selecting hotel {first_hotel.get('hotelId')}")

                if "bookHotel" in intents:
                     mock_guests = [{"name": f"Guest {i+1}", "id": str(uuid.uuid4())} for i in range(entities.get("guests", 1))]
                     booking_payload = {
                         "hotelId": first_hotel.get("hotelId"),
                         "guestDetails": mock_guests,
                         "roomType": "Standard" # Mock default
                     }
                     booking_response = call_agent_api(HOTEL_AGENT_URL, "bookHotel", booking_payload)
                     if "error" in booking_response:
                          results["details"]["errors"].append(f"Hotel booking failed: {booking_response['error']}")
                     elif booking_response.get("status") == "Confirmed":
                          results["details"]["hotelBookingId"] = booking_response.get("bookingId")
                          print(f"[PlannerAgent] Hotel booking confirmed: {results['details']['hotelBookingId']}")
                     else:
                          results["details"]["errors"].append(f"Hotel booking status: {booking_response.get('status', 'Unknown')}")
            else:
                 results["details"]["errors"].append("No hotels found matching criteria.")


    # --- Car Rental Handling ---
    if "searchCars" in intents:
        car_payload = {
            "location": entities.get("location"), # Use general location
            "pickupDate": entities.get("pickupDate"),
            "dropoffDate": entities.get("dropoffDate"),
            "carType": entities.get("carType") # Optional
        }
        # Validation for car search
        required_car_fields = ["location", "pickupDate", "dropoffDate"]
        missing_car_fields = [field for field in required_car_fields if not car_payload.get(field)]

        if missing_car_fields:
             error_msg = f"Missing required car rental details: {', '.join(missing_car_fields)}."
             results["details"]["errors"].append(error_msg)
             print(f"[PlannerAgent] Validation Error: {error_msg}") # Add log
        else:
            search_response = call_agent_api(CAR_AGENT_URL, "searchCars", car_payload)
            if "error" in search_response:
                results["details"]["errors"].append(f"Car search failed: {search_response['error']}")
            elif search_response.get("cars"):
                # ** MOCK DECISION: Just pick the first car found **
                first_car = search_response["cars"][0]
                print(f"[PlannerAgent] Mock Decision: Selecting car {first_car.get('carId')}")

                if "bookCar" in intents:
                     mock_driver = {"name": "Primary Driver", "id": str(uuid.uuid4())}
                     booking_payload = {
                         "carId": first_car.get("carId"),
                         "driverDetails": mock_driver
                     }
                     booking_response = call_agent_api(CAR_AGENT_URL, "bookCar", booking_payload)
                     if "error" in booking_response:
                          results["details"]["errors"].append(f"Car booking failed: {booking_response['error']}")
                     elif booking_response.get("status") == "Confirmed":
                          results["details"]["carRentalBookingId"] = booking_response.get("bookingId")
                          print(f"[PlannerAgent] Car rental booking confirmed: {results['details']['carRentalBookingId']}")
                     else:
                          results["details"]["errors"].append(f"Car rental booking status: {booking_response.get('status', 'Unknown')}")
            else:
                 results["details"]["errors"].append("No cars found matching criteria.")


    # 4. Finalize Response
    booked_items = []
    if results["details"]["flightBookingId"]: booked_items.append("Flight")
    if results["details"]["hotelBookingId"]: booked_items.append("Hotel")
    if results["details"]["carRentalBookingId"]: booked_items.append("Car Rental")

    if booked_items and not results["details"]["errors"]:
        results["status"] = "Success"
        results["summary"] = f"Successfully booked: {', '.join(booked_items)}."
    elif booked_items:
         results["status"] = "Partial Success"
         results["summary"] = f"Booked: {', '.join(booked_items)}. Encountered errors: {len(results['details']['errors'])}: {'; '.join(results['details']['errors'])}" # Include errors in summary
    elif results["details"]["errors"]:
        results["status"] = "Failed"
        results["summary"] = f"Planning failed. Errors: {len(results['details']['errors'])}: {'; '.join(results['details']['errors'])}" # Include errors in summary
    else:
        # Check if any intents were identified at all
        if not intents:
             results["status"] = "Failed"
             results["summary"] = "Could not understand the request or identify any services to book."
        else:
             results["status"] = "Failed" # Or "Needs Clarification"
             results["summary"] = "Could not fulfill the request. No services were successfully searched or booked."


    print(f"[PlannerAgent] Final planning result: {results}")
    return jsonify(results)


# --- Main Execution ---
if __name__ == '__main__':
    print(f"--- TripMaster AI Planner Agent ---")
    print(f"Running on {AGENT_BASE_URL}")
    print(f"Access Agent Card at: {AGENT_BASE_URL}/agent-card")
    print(f"Specialist Agents Expected At:")
    print(f"  Flight: {FLIGHT_AGENT_URL}")
    print(f"  Hotel:  {HOTEL_AGENT_URL}")
    print(f"  Car:    {CAR_AGENT_URL}")
    # Set debug=True for more detailed logs during development/debugging
    app.run(port=AGENT_PORT, debug=True)

