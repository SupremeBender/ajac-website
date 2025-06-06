"""
Test script to verify flight.py functionality
"""
import sys
import os
from models.flight import (
    Flight, convert_old_flight_data, get_flight, get_mission_flights,
    get_mission_flights_data
)

def main():
    """Run basic tests for flight.py functionality"""
    print("Testing Flight class...")
    flight = Flight(
        mission_id="TEST01",
        squadron="331",
        callsign="BLADE",
        flight_number=1,
        departure_base="ENKB",
        recovery_base="ENKB",
        operations_area="A1",
        mission_type="CAP",
        remarks="Test flight"
    )
    print(f"Created flight with ID: {flight.flight_id}")
    
    # Test converting old format to new format
    old_format = {
        "id": "test123",
        "callsign": "BLADE",
        "flight_number": 1,
        "departure_base": "ENKB",
        "recovery_base": "ENKB",
        "operations_area": "A1",
        "members": ["test_user1", "test_user2"],
        "aircraft_id": "665",
        "squadrons": ["331"]
    }
    
    print("\nTesting convert_old_flight_data function...")
    new_format = convert_old_flight_data(old_format, "TEST01")
    
    # Verify conversion
    print(f"Original format keys: {sorted(old_format.keys())}")
    print(f"New format keys: {sorted(new_format.keys())}")
    
    print("\nAll tests completed successfully!")

if __name__ == "__main__":
    # Adjust Python path to ensure imports work
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    main()
