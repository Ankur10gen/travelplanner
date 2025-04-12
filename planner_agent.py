import datetime
import re
import requests # Library to make HTTP requests
import uuid # Needed for mock passenger/driver details generation
import json # To parse LLM JSON response
from flask import Flask, request, jsonify

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Agent Configuration ---
AGENT_PORT = 5000 # Run this agent on port 5000
AGENT_BASE_URL = f"http://127.0.0.1:{AGENT_PORT}"

# --- Configuration for Specialist Agents ---
FLIGHT_AGENT_URL = "http://127.0.0.1:5001"
HOTEL_AGENT_URL = "http://127.0.0.1:5002"
CAR_AGENT_URL = "http://127.0.0.1:5003"

# --- Configuration for Local LLM ---
# Adjust this URL if your local LLM server (Ollama, LM Studio) runs elsewhere
LOCAL_LLM_API_URL = "http://172.24.128.1:11434/api/chat" # Use the IP from resolv.conf"
# Adjust this to the specific model you have downloaded and want to use with Ollama
# Example models: "llama3:8b", "phi3:mini", "mistral"
LOCAL_LLM_MODEL = "llama3:8b" # <<< CHANGE THIS TO YOUR DOWNLOADED OLLAMA MODEL

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
        }
    ]
}

# --- LLM Interaction Function ---

def call_local_llm(query):
    """
    Calls a locally running LLM (via Ollama API) to parse the query.
    """
    print(f"[PlannerAgent] Calling local LLM ({LOCAL_LLM_MODEL}) at {LOCAL_LLM_API_URL} for query: '{query}'")

    # --- Prompt Engineering ---
    # This prompt instructs the LLM to act as a travel planner's assistant,
    # identify intents and entities, and return them as JSON.
    # You may need to refine this prompt based on the specific LLM you use.
    prompt = f"""
You are an expert travel planning assistant. Analyze the following user request and extract the key information needed to book a trip.
Identify the user's intents (what they want to book: flights, hotels, cars) and extract the relevant entities for each intent.

User Request: "{query}"

Entities to extract:
- "origin": Departure city/airport for flights (string, null if not specified)
- "destination": Arrival city/airport for flights (string, null if not specified)
- "departureDate": Flight departure date in YYYY-MM-DD format (string, null if not specified)
- "returnDate": Flight return date in YYYY-MM-DD format (string, null if flight is one-way or not specified)
- "passengers": Number of people travelling for flights (integer, default 1 if not specified)
- "location": General location for hotel search or car rental pickup (string, often the destination city, null if not specified)
- "checkInDate": Hotel check-in date in YYYY-MM-DD format (string, null if not specified, often same as departureDate)
- "checkOutDate": Hotel check-out date in YYYY-MM-DD format (string, null if not specified, often same as returnDate)
- "guests": Number of guests for hotel booking (integer, default 1 if not specified, often same as passengers)
- "hotel_location_preference": Specific hotel location preference like "near Eiffel Tower" (string, null if not specified)
- "pickupDate": Car rental pickup date and time in YYYY-MM-DDTHH:mm:ssZ format (string, null if not specified, often same day as departureDate, use 12:00:00Z for time if unspecified)
- "dropoffDate": Car rental dropoff date and time in YYYY-MM-DDTHH:mm:ssZ format (string, null if not specified, often same day as returnDate, use 12:00:00Z for time if unspecified)
- "carType": Preferred type of rental car like "SUV", "Compact" (string, null if not specified)

Intents to identify (list of strings):
- "searchFlights"
- "bookFlight"
- "searchHotels"
- "bookHotel"
- "searchCars"
- "bookCar"
(Include 'book' intents if the user implies booking, like using the word "book" or "reserve")

Today's date is {datetime.date.today().strftime('%Y-%m-%d')}. Use this to resolve relative dates like "tomorrow" or "next week" (assume 'next week' starts on the upcoming Monday).

Return the identified intents and extracted entities strictly in the following JSON format. Do not include any explanations or introductory text outside the JSON structure itself.

{{
  "intents": ["list", "of", "intent", "strings"],
  "entities": {{
    "origin": "...",
    "destination": "...",
    "departureDate": "...",
    "returnDate": "...",
    "passengers": ...,
    "location": "...",
    "checkInDate": "...",
    "checkOutDate": "...",
    "guests": ...,
    "hotel_location_preference": "...",
    "pickupDate": "...",
    "dropoffDate": "...",
    "carType": "..."
  }}
}}
"""

    headers = {'Content-Type': 'application/json'}
    # Structure payload for Ollama /api/chat endpoint
    payload = {
        "model": LOCAL_LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that extracts travel information and responds ONLY in JSON format."},
            {"role": "user", "content": prompt}
        ],
        "format": "json", # Request JSON output format from Ollama
        "stream": False # Get the full response at once
    }

    try:
        response = requests.post(LOCAL_LLM_API_URL, json=payload, headers=headers, timeout=60) # Increased timeout for LLM
        response.raise_for_status()

        # Assuming the LLM respects the format instruction and returns JSON in the 'content' of the 'message'
        response_data = response.json()
        # Ollama's response structure for non-streaming chat puts the message object directly in the response
        message_content = response_data.get("message", {}).get("content", "")

        print(f"[PlannerAgent] Raw LLM Response Content:\n{message_content}") # Log raw response

        # Attempt to parse the JSON content string from the LLM response
        try:
            # The message_content itself should be the JSON string when format="json" is used
            parsed_json = json.loads(message_content)
            intents = set(parsed_json.get("intents", []))
            entities = parsed_json.get("entities", {})

            # Basic validation/sanitization (ensure numbers are ints, provide defaults if missing)
            # Use .get with default before converting to int to avoid errors if key is missing
            entities["passengers"] = int(entities.get("passengers", 1) or 1)
            entities["guests"] = int(entities.get("guests", 1) or 1)
            # Ensure nulls/empty strings from LLM are represented as None in Python
            for key, value in entities.items():
                 if value == "null" or value == "":
                      entities[key] = None

            print(f"[PlannerAgent] Parsed LLM Results - Intents: {intents}, Entities: {entities}")
            # Add a check for empty results after parsing
            if not intents and not any(entities.values()):
                 print("[PlannerAgent] Warning: LLM parsing resulted in empty intents and entities.")
                 # Optionally return an error or default values here
                 # For now, return empty sets/dicts as before
                 return set(), {}

            return intents, entities

        except json.JSONDecodeError as json_err:
            print(f"[PlannerAgent] Error: Failed to parse JSON from LLM response: {json_err}")
            print(f"[PlannerAgent] LLM Raw Content was: {message_content}")
            return set(), {} # Return empty results on parsing failure
        except Exception as e:
             print(f"[PlannerAgent] Error processing LLM response content: {e}")
             return set(), {}


    except requests.exceptions.RequestException as e:
        print(f"[PlannerAgent] Error calling local LLM API at {LOCAL_LLM_API_URL}: {e}")
        return set(), {} # Return empty results on API call failure
    except Exception as e:
        print(f"[PlannerAgent] Unexpected error during LLM call: {e}")
        return set(), {}


# --- Simulation Function (Kept for reference) ---
def simulate_llm_parse_query(query):
    """
    ** MOCK FUNCTION - NO LONGER USED BY DEFAULT **
    Simulates an LLM parsing the user query to extract intents and entities.
    """
    # ... (previous simulation code remains here, but won't be called) ...
    print("** Warning: Using MOCK simulate_llm_parse_query function! **")
    # ... (rest of simulation logic) ...
    # This function is kept for fallback or comparison but call_local_llm is used in plan_trip
    return set(), {} # Return empty for safety if called accidentally


# --- API Call Helper ---
def call_agent_api(base_url, capability_path, payload):
    """Helper function to call another agent's API endpoint."""
    url = f"{base_url}/{capability_path}"
    headers = {'Content-Type': 'application/json'}
    # Filter out None values from payload before sending
    payload_to_send = {k: v for k, v in payload.items() if v is not None}
    try:
        print(f"[PlannerAgent] Calling {url} with payload: {payload_to_send}")
        response = requests.post(url, json=payload_to_send, headers=headers, timeout=10) # 10 second timeout
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

    # 1. Call Local LLM for Parsing (Replaces simulation)
    # intents, entities = simulate_llm_parse_query(query) # Old way
    intents, entities = call_local_llm(query) # New way

    # Check if LLM call was successful and returned usable data
    # Check if entities dict exists and has values, or if intents set has items
    if not intents and (not entities or not any(entities.values())):
         # Handle case where LLM call failed or returned empty/invalid data
         print("[PlannerAgent] LLM processing failed or returned empty results. Aborting plan.")
         return jsonify({
             "status": "Failed",
             "summary": "Failed to process request using the local LLM. Check Planner Agent logs for details.",
             "details": {"errors": ["LLM processing failed or returned no usable data."]}
         }), 500


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

    # 3. Call Specialist Agents based on Intents (Logic remains largely the same)

    # --- Flight Handling ---
    if "searchFlights" in intents:
        flight_payload = {
            "origin": entities.get("origin"),
            "destination": entities.get("destination"),
            "departureDate": entities.get("departureDate"),
            "returnDate": entities.get("returnDate"), # Include if round trip implied/found
            "passengers": entities.get("passengers")
        }
        required_flight_fields = ["origin", "destination", "departureDate", "passengers"]
        # Use .get() on the entities dict for safety during validation
        missing_fields = [field for field in required_flight_fields if not entities.get(field)]

        if missing_fields:
             error_msg = f"Missing required flight details (from LLM output): {', '.join(missing_fields)}."
             results["details"]["errors"].append(error_msg)
             print(f"[PlannerAgent] Validation Error: {error_msg}")
        else:
            search_response = call_agent_api(FLIGHT_AGENT_URL, "searchFlights", flight_payload)
            if "error" in search_response:
                results["details"]["errors"].append(f"Flight search failed: {search_response['error']}")
            elif search_response.get("flights"):
                # Check if flights list is not empty
                if search_response["flights"]:
                    first_flight = search_response["flights"][0]
                    print(f"[PlannerAgent] Mock Decision: Selecting flight {first_flight.get('flightId')}")

                    if "bookFlight" in intents:
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
                    # Handle case where search returned empty list
                    results["details"]["errors"].append("Flight search returned no available flights.")
                    print("[PlannerAgent] Flight search returned no available flights.")
            else:
                 # Handle case where the 'flights' key is missing in the response
                 results["details"]["errors"].append("Flight search response was invalid (missing 'flights' key).")
                 print("[PlannerAgent] Flight search response was invalid.")


    # --- Hotel Handling ---
    if "searchHotels" in intents:
        hotel_payload = {
            "location": entities.get("hotel_location_preference") or entities.get("location"),
            "checkInDate": entities.get("checkInDate"),
            "checkOutDate": entities.get("checkOutDate"),
            "guests": entities.get("guests")
        }
        required_hotel_fields = ["location", "checkInDate", "checkOutDate", "guests"]
        missing_hotel_fields = [field for field in required_hotel_fields if not entities.get(field)]

        if missing_hotel_fields:
             error_msg = f"Missing required hotel details (from LLM output): {', '.join(missing_hotel_fields)}."
             results["details"]["errors"].append(error_msg)
             print(f"[PlannerAgent] Validation Error: {error_msg}")
        else:
            search_response = call_agent_api(HOTEL_AGENT_URL, "searchHotels", hotel_payload)
            if "error" in search_response:
                results["details"]["errors"].append(f"Hotel search failed: {search_response['error']}")
            elif search_response.get("hotels"):
                if search_response["hotels"]:
                    first_hotel = search_response["hotels"][0]
                    print(f"[PlannerAgent] Mock Decision: Selecting hotel {first_hotel.get('hotelId')}")

                    if "bookHotel" in intents:
                        mock_guests = [{"name": f"Guest {i+1}", "id": str(uuid.uuid4())} for i in range(entities.get("guests", 1))]
                        booking_payload = {
                            "hotelId": first_hotel.get("hotelId"),
                            "guestDetails": mock_guests,
                            "roomType": "Standard"
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
                    results["details"]["errors"].append("Hotel search returned no available hotels.")
                    print("[PlannerAgent] Hotel search returned no available hotels.")
            else:
                 results["details"]["errors"].append("Hotel search response was invalid (missing 'hotels' key).")
                 print("[PlannerAgent] Hotel search response was invalid.")


    # --- Car Rental Handling ---
    if "searchCars" in intents:
        car_payload = {
            "location": entities.get("location"),
            "pickupDate": entities.get("pickupDate"),
            "dropoffDate": entities.get("dropoffDate"),
            "carType": entities.get("carType")
        }
        required_car_fields = ["location", "pickupDate", "dropoffDate"]
        missing_car_fields = [field for field in required_car_fields if not entities.get(field)]

        if missing_car_fields:
             error_msg = f"Missing required car rental details (from LLM output): {', '.join(missing_car_fields)}."
             results["details"]["errors"].append(error_msg)
             print(f"[PlannerAgent] Validation Error: {error_msg}")
        else:
            search_response = call_agent_api(CAR_AGENT_URL, "searchCars", car_payload)
            if "error" in search_response:
                results["details"]["errors"].append(f"Car search failed: {search_response['error']}")
            elif search_response.get("cars"):
                if search_response["cars"]:
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
                    results["details"]["errors"].append("Car search returned no available cars.")
                    print("[PlannerAgent] Car search returned no available cars.")
            else:
                 results["details"]["errors"].append("Car search response was invalid (missing 'cars' key).")
                 print("[PlannerAgent] Car search response was invalid.")


    # 4. Finalize Response (Logic remains the same)
    booked_items = []
    if results["details"]["flightBookingId"]: booked_items.append("Flight")
    if results["details"]["hotelBookingId"]: booked_items.append("Hotel")
    if results["details"]["carRentalBookingId"]: booked_items.append("Car Rental")

    # Determine final status based on bookings and errors
    if booked_items and not results["details"]["errors"]:
        results["status"] = "Success"
        results["summary"] = f"Successfully booked: {', '.join(booked_items)}."
    elif booked_items: # Some booked, but errors occurred
         results["status"] = "Partial Success"
         results["summary"] = f"Booked: {', '.join(booked_items)}. Encountered errors: {len(results['details']['errors'])}: {'; '.join(results['details']['errors'])}"
    elif results["details"]["errors"]: # No bookings, only errors
        results["status"] = "Failed"
        results["summary"] = f"Planning failed. Errors: {len(results['details']['errors'])}: {'; '.join(results['details']['errors'])}"
    else: # No bookings and no errors (e.g., LLM found no intents, or search returned nothing)
        if not intents:
             results["status"] = "Failed"
             results["summary"] = "Could not understand the request or identify any services to book (LLM parsing issue)."
        else:
             results["status"] = "Failed"
             results["summary"] = "Could not fulfill the request. No services found matching criteria or no booking attempted."


    print(f"[PlannerAgent] Final planning result: {results}")
    return jsonify(results)


# --- Main Execution ---
if __name__ == '__main__':
    print(f"--- TripMaster AI Planner Agent (Using Local LLM: {LOCAL_LLM_MODEL}) ---")
    print(f"Running on {AGENT_BASE_URL}")
    print(f"Expecting Local LLM API at: {LOCAL_LLM_API_URL}")
    print(f"Access Agent Card at: {AGENT_BASE_URL}/agent-card")
    print(f"Specialist Agents Expected At:")
    print(f"  Flight: {FLIGHT_AGENT_URL}")
    print(f"  Hotel:  {HOTEL_AGENT_URL}")
    print(f"  Car:    {CAR_AGENT_URL}")
    # Set debug=True for more detailed logs during development/debugging
    app.run(port=AGENT_PORT, debug=True)

