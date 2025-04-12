import datetime
import re
import requests # Library to make HTTP requests
import uuid
import json
import threading # For locking during discovery
from flask import Flask, request, jsonify

# --- Flask App Initialization ---
app = Flask(__name__)

# --- Agent Configuration ---
AGENT_PORT = 5000 # Run this agent on port 5000
AGENT_BASE_URL = f"http://127.0.0.1:{AGENT_PORT}"

# --- Configuration for Local LLM ---
WINDOWS_HOST_IP = "172.24.128.1" # <<< Make sure this is the correct IP from `ip route`
LOCAL_LLM_API_URL = f"http://{WINDOWS_HOST_IP}:11434/api/chat"
LOCAL_LLM_MODEL = "llama3:8b" # <<< CHANGE THIS TO YOUR DOWNLOADED OLLAMA MODEL

# --- Configuration for Specialist Agent Discovery ---
SPECIALIST_AGENT_BASE_URLS = [
    "http://127.0.0.1:5001", # Flight Agent expected port
    "http://127.0.0.1:5002", # Hotel Agent expected port
    "http://127.0.0.1:5003"  # Car Agent expected port
]

# --- Agent Registry & Discovery State ---
agent_registry = {}
discovery_lock = threading.Lock() # Use a standard lock
discovery_attempted = False

# --- Agent Card Definition (Planner's Own Card) ---
AGENT_CARD = {
    "agentId": "travel-planner-001",
    "displayName": "TripMaster AI Planner",
    "description": "Coordinates flight, hotel, and car rental bookings based on user travel requests.",
    "endpointUrl": AGENT_BASE_URL,
    "capabilities": [
        {
          "capabilityId": "planTrip",
          "description": "Takes a natural language travel request...",
          "path": "/planTrip"
        }
    ]
}

# --- Agent Discovery Function ---
def discover_agents():
    """
    Fetches Agent Cards from known specialist agent base URLs
    and populates the agent_registry.
    NOTE: This function assumes it's called within the discovery_lock context.
    """
    global agent_registry # We will modify the global registry directly
    print("[PlannerAgent] Starting agent discovery...")
    discovered_agents = {} # Temporary dict for this discovery run

    for base_url in SPECIALIST_AGENT_BASE_URLS:
        agent_card_url = f"{base_url}/agent-card"
        try:
            print(f"[PlannerAgent] Attempting to discover agent at: {agent_card_url}")
            response = requests.get(agent_card_url, timeout=5)
            response.raise_for_status()
            agent_card = response.json()
            agent_id = agent_card.get("agentId")
            endpoint_url = agent_card.get("endpointUrl")
            capabilities = agent_card.get("capabilities", [])
            if agent_id and endpoint_url and capabilities:
                agent_info = {
                    "agentId": agent_id,
                    "displayName": agent_card.get("displayName", agent_id),
                    "endpointUrl": endpoint_url,
                    "capabilities": {cap.get("capabilityId"): cap for cap in capabilities if cap.get("capabilityId")}
                }
                discovered_agents[agent_id] = agent_info # Add to temporary dict first
                print(f"[PlannerAgent] Successfully discovered: {agent_info['displayName']} ({agent_id})")
            else:
                print(f"[PlannerAgent] Warning: Invalid agent card format received from {base_url}")
        except requests.exceptions.RequestException as e:
            print(f"[PlannerAgent] Warning: Failed to connect or get agent card from {base_url}: {e}")
        except json.JSONDecodeError:
             print(f"[PlannerAgent] Warning: Failed to parse JSON agent card from {base_url}")
        except Exception as e:
            print(f"[PlannerAgent] Warning: Unexpected error during discovery for {base_url}: {e}")

    # --- Modification: Update global registry directly ---
    # The outer lock in ensure_discovery already protects this section
    # No need for: with discovery_lock:
    agent_registry.update(discovered_agents) # Update the main registry

    print(f"[PlannerAgent] Agent discovery finished. Registry content: {json.dumps(agent_registry, indent=2)}")


def ensure_discovery():
    """Ensures agent discovery has been attempted at least once."""
    global discovery_attempted
    # Quick check without lock first for performance
    if not discovery_attempted:
        # Acquire lock only if discovery might be needed
        with discovery_lock:
            # Double check inside lock to prevent race condition
            if not discovery_attempted:
                discover_agents() # This call is protected by the lock
                discovery_attempted = True # Mark as done *after* discovery finishes
                print("[PlannerAgent] Discovery attempt marked as done.")


def find_agent_for_capability(capability_id):
    """
    Searches the registry for an agent that provides the specified capability.
    Returns the agent's endpointUrl and the capability's specific path, or (None, None).
    """
    ensure_discovery() # Make sure discovery has run at least once
    # Access registry safely - although reads are often thread-safe in Python dicts,
    # locking ensures we read after discovery is fully complete.
    # However, since ensure_discovery blocks until done, we might not strictly need the lock here for reads.
    # Let's keep it simple for now without a lock here, assuming reads are safe after ensure_discovery completes.
    # If concurrency issues arise later, add 'with discovery_lock:' around the loop.
    for agent_id, agent_info in agent_registry.items(): # Read from registry
        if capability_id in agent_info.get("capabilities", {}):
            capability_info = agent_info["capabilities"][capability_id]
            endpoint_url = agent_info.get("endpointUrl")
            capability_path = capability_info.get("path")
            if endpoint_url and capability_path:
                print(f"[PlannerAgent] Found capability '{capability_id}' at agent '{agent_id}' ({endpoint_url}{capability_path})")
                return endpoint_url, capability_path
            else:
                 print(f"[PlannerAgent] Warning: Found capability '{capability_id}' for agent '{agent_id}' but missing endpointUrl or path.")
    print(f"[PlannerAgent] Warning: Capability '{capability_id}' not found in any registered agent.")
    return None, None


# --- LLM Interaction Function (call_local_llm - unchanged) ---
def call_local_llm(query):
    print(f"[PlannerAgent] DEBUG: Entering call_local_llm function for query: '{query}'")
    print(f"[PlannerAgent] Calling local LLM ({LOCAL_LLM_MODEL}) at {LOCAL_LLM_API_URL} for query: '{query}'")
    prompt = f"""
You are an expert travel planning assistant. Analyze the following user request and extract the key information needed to book a trip.
Identify the user's intents (what they want to book: flights, hotels, cars) and extract the relevant entities for each intent.

User Request: "{query}"

Entities to extract:
- "origin": Departure city/airport for flights (string, null if not specified)
- "destination": Arrival city/airport for flights (string, null if not specified)
- "departureDate": Flight departure date in<y_bin_46>-MM-DD format (string, null if not specified)
- "returnDate": Flight return date in<y_bin_46>-MM-DD format (string, null if flight is one-way or not specified)
- "passengers": Number of people travelling for flights (integer, default 1 if not specified)
- "location": General location for hotel search or car rental pickup (string, often the destination city, null if not specified)
- "checkInDate": Hotel check-in date in<y_bin_46>-MM-DD format (string, null if not specified, often same as departureDate)
- "checkOutDate": Hotel check-out date in<y_bin_46>-MM-DD format (string, null if not specified, often same as returnDate)
- "guests": Number of guests for hotel booking (integer, default 1 if not specified, often same as passengers)
- "hotel_location_preference": Specific hotel location preference like "near Eiffel Tower" (string, null if not specified)
- "pickupDate": Car rental pickup date and time in<y_bin_46>-MM-DDTHH:mm:ssZ format (string, null if not specified, often same day as departureDate, use 12:00:00Z for time if unspecified)
- "dropoffDate": Car rental dropoff date and time in<y_bin_46>-MM-DDTHH:mm:ssZ format (string, null if not specified, often same day as returnDate, use 12:00:00Z for time if unspecified)
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
    payload = {
        "model": LOCAL_LLM_MODEL,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that extracts travel information and responds ONLY in JSON format."},
            {"role": "user", "content": prompt}
        ],
        "format": "json",
        "stream": False
    }
    try:
        print(f"[PlannerAgent] DEBUG: About to send request to LLM API: {LOCAL_LLM_API_URL}")
        response = requests.post(LOCAL_LLM_API_URL, json=payload, headers=headers, timeout=60)
        response.raise_for_status()
        response_data = response.json()
        print(f"[PlannerAgent] DEBUG: Received response from LLM API. Status: {response.status_code}")
        message_content = response_data.get("message", {}).get("content", "")
        print(f"[PlannerAgent] Raw LLM Response Content:\n{message_content}")
        try:
            parsed_json = json.loads(message_content)
            intents = set(parsed_json.get("intents", []))
            entities = parsed_json.get("entities", {})
            entities["passengers"] = int(entities.get("passengers", 1) or 1)
            entities["guests"] = int(entities.get("guests", 1) or 1)
            for key, value in entities.items():
                 if value == "null" or value == "":
                      entities[key] = None
            print(f"[PlannerAgent] Parsed LLM Results - Intents: {intents}, Entities: {entities}")
            if not intents and not any(entities.values()):
                 print("[PlannerAgent] Warning: LLM parsing resulted in empty intents and entities.")
                 return set(), {}
            print(f"[PlannerAgent] DEBUG: Exiting call_local_llm successfully.")
            return intents, entities
        except json.JSONDecodeError as json_err:
            print(f"[PlannerAgent] Error: Failed to parse JSON from LLM response: {json_err}")
            print(f"[PlannerAgent] LLM Raw Content was: {message_content}")
            return set(), {}
        except Exception as e:
             print(f"[PlannerAgent] Error processing LLM response content: {e}")
             return set(), {}
    except requests.exceptions.RequestException as e:
        print(f"[PlannerAgent] Error calling local LLM API at {LOCAL_LLM_API_URL}: {e}")
        return set(), {}
    except Exception as e:
        print(f"[PlannerAgent] Unexpected error during LLM call: {e}")
        return set(), {}


# --- API Call Helper (Unchanged) ---
def call_agent_api(base_url, capability_path, payload):
    if not capability_path.startswith('/'):
         capability_path = '/' + capability_path
    url = f"{base_url.rstrip('/')}{capability_path}"
    headers = {'Content-Type': 'application/json'}
    payload_to_send = {k: v for k, v in payload.items() if v is not None}
    try:
        print(f"[PlannerAgent] Calling {url} with payload: {payload_to_send}")
        response = requests.post(url, json=payload_to_send, headers=headers, timeout=10)
        response.raise_for_status()
        print(f"[PlannerAgent] Received response from {url}: Status {response.status_code}")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"[PlannerAgent] Error calling {url}: {e}")
        return {"error": f"Failed to call API: {e}"}
    except Exception as e:
        print(f"[PlannerAgent] Unexpected error during API call to {url}: {e}")
        return {"error": f"Unexpected error calling API: {e}"}


# --- API Endpoints ---

@app.route('/agent-card', methods=['GET'])
def get_agent_card():
    return jsonify(AGENT_CARD)

@app.route('/planTrip', methods=['POST'])
def plan_trip():
    data = request.get_json()
    if not data or 'query' not in data:
        return jsonify({"error": "Invalid JSON payload, 'query' field required"}), 400

    query = data['query']
    print(f"\n[PlannerAgent] Received planning request: '{query}'")

    # --- Ensure agents are discovered ---
    print("[PlannerAgent] DEBUG: Calling ensure_discovery()...")
    ensure_discovery()
    print("[PlannerAgent] DEBUG: Returned from ensure_discovery().")

    print(f"[PlannerAgent] DEBUG: Checking agent registry (size: {len(agent_registry)})...")
    if not agent_registry:
         print("[PlannerAgent] No specialist agents found in registry. Cannot proceed.")
         results = {
            "status": "Failed",
            "summary": "Configuration error: No specialist agents discovered.",
            "details": {"errors": ["Failed to discover specialist agents."]}
         }
         return jsonify(results), 500
    print("[PlannerAgent] DEBUG: Agent registry check passed.")

    # 1. Call Local LLM for Parsing
    print("[PlannerAgent] DEBUG: About to call call_local_llm()...")
    intents, entities = call_local_llm(query)
    print("[PlannerAgent] DEBUG: Returned from call_local_llm().")
    print(f"[PlannerAgent] DEBUG: Intents from LLM: {intents}")
    print(f"[PlannerAgent] DEBUG: Entities from LLM: {entities}")


    if not intents and (not entities or not any(entities.values())):
         print("[PlannerAgent] LLM processing failed or returned empty results. Aborting plan.")
         return jsonify({
             "status": "Failed",
             "summary": "Failed to process request using the local LLM. Check Planner Agent logs for details.",
             "details": {"errors": ["LLM processing failed or returned no usable data."]}
         }), 500
    print("[PlannerAgent] DEBUG: LLM result check passed.")

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
    print("[PlannerAgent] DEBUG: Prepared results structure.")

    # 3. Call Specialist Agents based on Intents using Dynamic Discovery
    print("[PlannerAgent] DEBUG: Starting specialist agent calls based on intents...")

    # --- Flight Handling ---
    if "searchFlights" in intents:
        print("[PlannerAgent] DEBUG: Handling 'searchFlights' intent...")
        agent_url, capability_path = find_agent_for_capability("searchFlights")
        if agent_url and capability_path:
            flight_payload = {
                "origin": entities.get("origin"),
                "destination": entities.get("destination"),
                "departureDate": entities.get("departureDate"),
                "returnDate": entities.get("returnDate"),
                "passengers": entities.get("passengers")
            }
            required_flight_fields = ["origin", "destination", "departureDate", "passengers"]
            missing_fields = [field for field in required_flight_fields if not entities.get(field)]

            if missing_fields:
                error_msg = f"Missing required flight details (from LLM output): {', '.join(missing_fields)}."
                results["details"]["errors"].append(error_msg)
                print(f"[PlannerAgent] Validation Error: {error_msg}")
            else:
                search_response = call_agent_api(agent_url, capability_path, flight_payload)
                if "error" in search_response:
                    results["details"]["errors"].append(f"Flight search failed: {search_response['error']}")
                elif search_response.get("flights"):
                    if search_response["flights"]:
                        first_flight = search_response["flights"][0]
                        print(f"[PlannerAgent] Mock Decision: Selecting flight {first_flight.get('flightId')}")
                        if "bookFlight" in intents:
                            print("[PlannerAgent] DEBUG: Handling 'bookFlight' intent...")
                            book_agent_url, book_capability_path = find_agent_for_capability("bookFlight")
                            if book_agent_url and book_capability_path:
                                mock_passengers = [{"name": f"Traveller {i+1}", "id": str(uuid.uuid4())} for i in range(entities.get("passengers", 1))]
                                booking_payload = {"flightId": first_flight.get("flightId"), "passengerDetails": mock_passengers}
                                booking_response = call_agent_api(book_agent_url, book_capability_path, booking_payload)
                                if "error" in booking_response: results["details"]["errors"].append(f"Flight booking failed: {booking_response['error']}")
                                elif booking_response.get("status") == "Confirmed": results["details"]["flightBookingId"] = booking_response.get("bookingId"); print(f"[PlannerAgent] Flight booking confirmed: {results['details']['flightBookingId']}")
                                else: results["details"]["errors"].append(f"Flight booking status: {booking_response.get('status', 'Unknown')}")
                            else: results["details"]["errors"].append("Could not find agent/path for 'bookFlight' capability.")
                    else: results["details"]["errors"].append("Flight search returned no available flights."); print("[PlannerAgent] Flight search returned no available flights.")
                else: results["details"]["errors"].append("Flight search response was invalid (missing 'flights' key)."); print("[PlannerAgent] Flight search response was invalid.")
        else:
            results["details"]["errors"].append("Could not find agent/path for 'searchFlights' capability.")

    # --- Hotel Handling ---
    # (Code structure similar to flight handling, using find_agent_for_capability)
    if "searchHotels" in intents:
        print("[PlannerAgent] DEBUG: Handling 'searchHotels' intent...")
        agent_url, capability_path = find_agent_for_capability("searchHotels")
        if agent_url and capability_path:
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
                search_response = call_agent_api(agent_url, capability_path, hotel_payload)
                if "error" in search_response:
                    results["details"]["errors"].append(f"Hotel search failed: {search_response['error']}")
                elif search_response.get("hotels"):
                    if search_response["hotels"]:
                        first_hotel = search_response["hotels"][0]
                        print(f"[PlannerAgent] Mock Decision: Selecting hotel {first_hotel.get('hotelId')}")
                        if "bookHotel" in intents:
                            print("[PlannerAgent] DEBUG: Handling 'bookHotel' intent...")
                            book_agent_url, book_capability_path = find_agent_for_capability("bookHotel")
                            if book_agent_url and book_capability_path:
                                mock_guests = [{"name": f"Guest {i+1}", "id": str(uuid.uuid4())} for i in range(entities.get("guests", 1))]
                                booking_payload = {"hotelId": first_hotel.get("hotelId"), "guestDetails": mock_guests, "roomType": "Standard"}
                                booking_response = call_agent_api(book_agent_url, book_capability_path, booking_payload)
                                if "error" in booking_response: results["details"]["errors"].append(f"Hotel booking failed: {booking_response['error']}")
                                elif booking_response.get("status") == "Confirmed": results["details"]["hotelBookingId"] = booking_response.get("bookingId"); print(f"[PlannerAgent] Hotel booking confirmed: {results['details']['hotelBookingId']}")
                                else: results["details"]["errors"].append(f"Hotel booking status: {booking_response.get('status', 'Unknown')}")
                            else: results["details"]["errors"].append("Could not find agent/path for 'bookHotel' capability.")
                    else: results["details"]["errors"].append("Hotel search returned no available hotels."); print("[PlannerAgent] Hotel search returned no available hotels.")
                else: results["details"]["errors"].append("Hotel search response was invalid (missing 'hotels' key)."); print("[PlannerAgent] Hotel search response was invalid.")
        else:
            results["details"]["errors"].append("Could not find agent/path for 'searchHotels' capability.")


    # --- Car Rental Handling ---
    # (Code structure similar to flight handling, using find_agent_for_capability)
    if "searchCars" in intents:
        print("[PlannerAgent] DEBUG: Handling 'searchCars' intent...")
        agent_url, capability_path = find_agent_for_capability("searchCars")
        if agent_url and capability_path:
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
                search_response = call_agent_api(agent_url, capability_path, car_payload)
                if "error" in search_response:
                    results["details"]["errors"].append(f"Car search failed: {search_response['error']}")
                elif search_response.get("cars"):
                    if search_response["cars"]:
                        first_car = search_response["cars"][0]
                        print(f"[PlannerAgent] Mock Decision: Selecting car {first_car.get('carId')}")
                        if "bookCar" in intents:
                             print("[PlannerAgent] DEBUG: Handling 'bookCar' intent...")
                             book_agent_url, book_capability_path = find_agent_for_capability("bookCar")
                             if book_agent_url and book_capability_path:
                                 mock_driver = {"name": "Primary Driver", "id": str(uuid.uuid4())}
                                 booking_payload = {"carId": first_car.get("carId"),"driverDetails": mock_driver}
                                 booking_response = call_agent_api(book_agent_url, book_capability_path, booking_payload)
                                 if "error" in booking_response: results["details"]["errors"].append(f"Car booking failed: {booking_response['error']}")
                                 elif booking_response.get("status") == "Confirmed": results["details"]["carRentalBookingId"] = booking_response.get("bookingId"); print(f"[PlannerAgent] Car rental booking confirmed: {results['details']['carRentalBookingId']}")
                                 else: results["details"]["errors"].append(f"Car rental booking status: {booking_response.get('status', 'Unknown')}")
                             else: results["details"]["errors"].append("Could not find agent/path for 'bookCar' capability.")
                    else: results["details"]["errors"].append("Car search returned no available cars."); print("[PlannerAgent] Car search returned no available cars.")
                else: results["details"]["errors"].append("Car search response was invalid (missing 'cars' key)."); print("[PlannerAgent] Car search response was invalid.")
        else:
            results["details"]["errors"].append("Could not find agent/path for 'searchCars' capability.")


    # 4. Finalize Response
    print("[PlannerAgent] DEBUG: Finalizing response...")
    booked_items = []
    if results["details"]["flightBookingId"]: booked_items.append("Flight")
    if results["details"]["hotelBookingId"]: booked_items.append("Hotel")
    if results["details"]["carRentalBookingId"]: booked_items.append("Car Rental")
    if booked_items and not results["details"]["errors"]:
        results["status"] = "Success"; results["summary"] = f"Successfully booked: {', '.join(booked_items)}."
    elif booked_items:
         results["status"] = "Partial Success"; results["summary"] = f"Booked: {', '.join(booked_items)}. Encountered errors: {len(results['details']['errors'])}: {'; '.join(results['details']['errors'])}"
    elif results["details"]["errors"]:
        results["status"] = "Failed"; results["summary"] = f"Planning failed. Errors: {len(results['details']['errors'])}: {'; '.join(results['details']['errors'])}"
    else:
        if not intents: results["status"] = "Failed"; results["summary"] = "Could not understand the request or identify any services to book (LLM parsing issue)."
        else: results["status"] = "Failed"; results["summary"] = "Could not fulfill the request. No services found matching criteria or no booking attempted."

    print(f"[PlannerAgent] Final planning result: {results}")
    return jsonify(results)


# --- Main Execution ---
if __name__ == '__main__':
    print(f"--- TripMaster AI Planner Agent (Using Local LLM: {LOCAL_LLM_MODEL}, Dynamic Discovery) ---")
    print(f"Running on {AGENT_BASE_URL}")
    print(f"Expecting Local LLM API at: {LOCAL_LLM_API_URL}")
    print(f"Will attempt discovery from: {SPECIALIST_AGENT_BASE_URLS}")
    print(f"Access Agent Card at: {AGENT_BASE_URL}/agent-card")
    app.run(port=AGENT_PORT, debug=True)

