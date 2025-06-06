"""
Simplified test for flight.py imports
"""
import os
import sys

def main():
    """Run basic import test"""
    try:
        from models.flight import Flight
        print("Successfully imported Flight class")
        
        flight = Flight(mission_id="TEST01")
        print(f"Successfully created Flight object with ID: {flight.flight_id}")
        
        print("Test passed!")
        return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    # Add parent directory to path
    sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
    sys.exit(main())
