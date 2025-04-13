![Workflow](plannerimg.png)

# Travel Planner Agent

```python
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
```

# Flight Agent:

```python
AGENT_CARD = {
    "agentId": "flight-booker-002",
    "displayName": "SkyHigh Flight Booker",
    "description": "Searches for and books airline tickets.",
    "endpointUrl": AGENT_BASE_URL, # Base URL for the agent
    "capabilities": [
        {
          "capabilityId": "searchFlights",
          "description": "Finds available flights based on criteria.",
          "path": "/searchFlights" # <<< ADDED: Specific path for this capability
          # Parameter/response schemas could be formally defined here too
        },
        {
          "capabilityId": "bookFlight",
          "description": "Books a specific flight identified by flightId.",
          "path": "/bookFlight" # <<< ADDED: Specific path for this capability
        }
    ],
    "definitions": { # Keeping definitions for potential future schema validation
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
```

## Book a flight and hotel to Tokyo from Singapore for 2 people next week

```python
raina@ankursmachine: $ curl -X POST http://127.0.0.1:5000/planTrip 
                            -H "Content-Type: application/json"      
                            -d '{
"query": "Book a flight and hotel to Tokyo from Singapore for 2 people next week"
                             }'

{
  "details": {
    "carRentalBookingId": null,
    "errors": [],
    "flightBookingId": "FLT-5e892121-0ec7-4519-a53a-05f4662f3d44",
    "hotelBookingId": null
  },
  "status": "Success",
  "summary": "Successfully booked: Flight."
}
```