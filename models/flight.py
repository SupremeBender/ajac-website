"""
Flight model for the signup module
"""
import json
import os
from datetime import datetime
from utils.storage import load_json, save_json
import logging
import uuid

logger = logging.getLogger(__name__)

class Flight:
    def __init__(self, mission_id, flight_id=None, squadron=None, callsign=None, 
                flight_number=None, departure_base=None, recovery_base=None, 
                operations_area=None, mission_type=None, remarks=None, aircraft_ids=None, 
                transponder_codes=None, tacan_channel=None, intraflight_freq=None,
                pilots=None, status="active", side="blue"):
        self.flight_id = flight_id or str(uuid.uuid4())
        self.mission_id = mission_id
        self.squadron = squadron
        self.callsign = callsign
        self.flight_number = flight_number
        self.departure_base = departure_base
        self.recovery_base = recovery_base
        self.operations_area = operations_area
        self.mission_type = mission_type
        self.remarks = remarks
        self.aircraft_ids = aircraft_ids or []
        self.transponder_codes = transponder_codes or []
        self.tacan_channel = tacan_channel
        self.intraflight_freq = intraflight_freq
        self.pilots = pilots or []
        self.status = status
        self.side = side
        self.created_at = datetime.now().isoformat()
    
    def to_dict(self):
        return {
            "flight_id": self.flight_id,
            "mission_id": self.mission_id,
            "squadron": self.squadron,
            "callsign": self.callsign,
            "flight_number": self.flight_number,
            "departure_base": self.departure_base,
            "recovery_base": self.recovery_base,
            "operations_area": self.operations_area,
            "mission_type": self.mission_type,
            "remarks": self.remarks,
            "aircraft_ids": self.aircraft_ids,
            "transponder_codes": self.transponder_codes,
            "tacan_channel": self.tacan_channel,
            "intraflight_freq": self.intraflight_freq,
            "pilots": self.pilots,
            "status": self.status,
            "side": self.side,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, data):
        flight = cls(
            mission_id=data["mission_id"],
            flight_id=data["flight_id"],
            squadron=data["squadron"],
            callsign=data["callsign"],
            flight_number=data["flight_number"],
            departure_base=data["departure_base"],
            recovery_base=data["recovery_base"],
            operations_area=data["operations_area"],
            mission_type=data.get("mission_type"),
            remarks=data.get("remarks"),
            aircraft_ids=data["aircraft_ids"],
            transponder_codes=data["transponder_codes"],
            tacan_channel=data["tacan_channel"],
            intraflight_freq=data["intraflight_freq"],
            pilots=data["pilots"],
            status=data["status"],
            side=data.get("side", "blue")
        )
        flight.created_at = data["created_at"]
        return flight

def create_flight(mission_id, flight_data, user_id, username):
    from utils.resources import get_squadrons, get_tacan_channel, get_intraflight_freq, get_aircraft_at_base
    from utils.storage import load_mission, save_mission
    import traceback
    logger.debug(f"[CREATE_FLIGHT] mission_id={mission_id}, flight_data={flight_data}, user_id={user_id}, username={username}")
    try:
        mission = load_mission(mission_id)
        if not mission:
            logger.error(f"Mission {mission_id} not found")
            raise ValueError(f"Mission {mission_id} not found")
        # Get all squadron callsigns
        squadrons = get_squadrons()
        squadron_id = flight_data["squadron"]
        callsign_bank = squadrons.get(squadron_id, {}).get("callsigns", [squadron_id])
        # Find all used callsigns and flight_numbers
        used_callsigns = set()
        used_numbers = set()
        if "flights" in mission:
            for f in mission["flights"].values():
                used_callsigns.add(f["callsign"])
                used_numbers.add(f["flight_number"])
        selected_callsign = None
        selected_number = None
        found = False
        for num in range(0, 9):  # 0-8 allowed
            for callsign in callsign_bank:
                if callsign not in used_callsigns and num not in used_numbers:
                    selected_callsign = callsign
                    selected_number = num
                    found = True
                    break
            if found:
                break
        if not found:
            raise ValueError("No available callsign/number pairs for this squadron")
        # Assign transponder codes using mission_type prefix and octal block
        mission_type = flight_data.get("mission_type", "NONE")
        remarks = flight_data.get("remarks", "")
        # Load mission_types.json for prefix
        mission_types_path = os.path.join(os.path.dirname(__file__), '../config/mission_types.json')
        with open(mission_types_path) as f:
            mission_types = json.load(f)
        prefix = mission_types.get(mission_type, {}).get("transponder", "00")
        # Each flight gets a block of 4 octal codes (00-03, 04-07, ...)
        block_start = selected_number * 4
        transponder_codes = []
        for i in range(4):
            octal = format(block_start + i, '02o')  # octal, 2 digits
            code = f"{prefix}{octal}"
            transponder_codes.append(code)
        logger.debug(f"[CREATE_FLIGHT] Assigned transponder_codes={transponder_codes}")
        # Get unique TACAN channel
        tacan_channel = get_tacan_channel(mission_id)
        logger.debug(f"[CREATE_FLIGHT] Assigned tacan_channel={tacan_channel}")
        # Get intraflight frequency
        intraflight_freq = get_intraflight_freq(mission_id)
        logger.debug(f"[CREATE_FLIGHT] Assigned intraflight_freq={intraflight_freq}")
        # Get aircraft for flight lead - require explicit aircraft selection
        aircraft_id = flight_data.get("aircraft_id")
        if not aircraft_id:
            raise ValueError("Aircraft must be selected")
        # Create the flight with the assigned data
        pilot_callsign = f"{selected_callsign}{selected_number}1"
        pilot_transponder = transponder_codes[0] if transponder_codes else None
        flight = Flight(
            mission_id=mission_id,
            squadron=squadron_id,
            callsign=selected_callsign,
            flight_number=selected_number,
            departure_base=flight_data["departure_base"],
            recovery_base=flight_data["recovery_base"],
            operations_area=flight_data["operations_area"],
            mission_type=mission_type,
            remarks=remarks,
            aircraft_ids=[aircraft_id],
            transponder_codes=transponder_codes,
            tacan_channel=tacan_channel,
            intraflight_freq=intraflight_freq,
            pilots=[{"user_id": user_id, "username": username, "nickname": username, "position": "1", "joined_at": datetime.now().isoformat(), "callsign": pilot_callsign, "transponder": pilot_transponder, "aircraft": aircraft_id}],
            side=flight_data.get("side", "blue")
        )
        logger.debug(f"[CREATE_FLIGHT] Flight object created: {flight.to_dict()}")
        # Add flight to mission
        if "flights" not in mission:
            mission["flights"] = {}
        mission["flights"][flight.flight_id] = flight.to_dict()
        logger.debug(f"[CREATE_FLIGHT] Mission structure before save: {mission}")
        save_mission(mission)
        logger.info(f"[CREATE_FLIGHT] Flight {flight.flight_id} created and saved successfully.")
        return flight
    except Exception as e:
        logger.error(f"[CREATE_FLIGHT] Exception: {e}\n{traceback.format_exc()}")
        raise

def save_flight(flight):
    """Save a flight to the mission's flight list"""
    from utils.storage import load_mission, save_mission
    
    # Load the mission
    mission = load_mission(flight.mission_id)
    if not mission:
        logger.error(f"Mission {flight.mission_id} not found")
        return False
    
    # Update or add flight to mission
    if "flights" not in mission:
        mission["flights"] = {}
    
    mission["flights"][flight.flight_id] = flight.to_dict()
    
    # Save the mission with the updated flight
    save_mission(mission)
    return True

def get_flight(flight_id, mission_id=None):
    """Get a flight by ID"""
    from utils.storage import load_mission, list_missions
    logger.debug(f"[get_flight] Searching for flight_id={flight_id} in mission_id={mission_id}")
    # If mission_id is provided, check only that mission
    if mission_id:
        mission = load_mission(mission_id)
        if mission and "flights" in mission:
            logger.debug(f"[get_flight] Available flight IDs in mission: {list(mission['flights'].keys())}")
            if flight_id in mission["flights"]:
                return Flight.from_dict(mission["flights"][flight_id])
        return None
    # Otherwise, check all missions
    missions = list_missions()
    for mission_id in missions:
        mission = load_mission(mission_id)
        if mission and "flights" in mission:
            logger.debug(f"[get_flight] Available flight IDs in mission {mission_id}: {list(mission['flights'].keys())}")
            if flight_id in mission["flights"]:
                return Flight.from_dict(mission["flights"][flight_id])
    logger.error(f"[get_flight] Flight {flight_id} not found in any mission")
    return None

def get_mission_flights(mission_id):
    """Get all flight IDs for a mission"""
    from utils.storage import load_mission
    
    mission = load_mission(mission_id)
    if not mission:
        return []
    
    if "flights" not in mission:
        return []
    
    return list(mission["flights"].keys())

def get_mission_flights_data(mission_id):
    """Get all flight data for a mission"""
    from utils.storage import load_mission
    
    mission = load_mission(mission_id)
    if not mission:
        return []
    
    if "flights" not in mission:
        return []
    
    flights = []
    for flight_data in mission["flights"].values():
        flights.append(Flight.from_dict(flight_data))
    
    return flights

def join_flight(flight_id, user_id, username, position, mission_id=None, aircraft=None):
    """Join a flight at the specified position, with selected aircraft"""
    flight = get_flight(flight_id, mission_id)
    if not flight:
        return None, "Flight not found"

    # Check if position is available
    positions = [p["position"] for p in flight.pilots]
    if position in positions:
        return None, f"Position {position} is already taken"

    # Check if user is already in flight
    if any(p["user_id"] == user_id for p in flight.pilots):
        return None, "You are already in this flight"

    # Ensure aircraft is provided
    if not aircraft:
        return None, "Aircraft must be selected"

    # Assign callsign and transponder code for this pilot
    try:
        pos_num = int(position)
    except Exception:
        pos_num = 0

    pilot_callsign = f"{flight.callsign}{flight.flight_number}{position}"
    pilot_transponder = None
    if flight.transponder_codes and 1 <= pos_num <= len(flight.transponder_codes):
        pilot_transponder = flight.transponder_codes[pos_num-1]

    # Save the selected aircraft
    pilot_aircraft = aircraft
    flight.pilots.append({
        "user_id": user_id,
        "username": username,
        "position": position,
        "joined_at": datetime.now().isoformat(),
        "callsign": pilot_callsign,
        "transponder": pilot_transponder,
        "aircraft": pilot_aircraft
    })

    save_flight(flight)
    return flight, "Successfully joined flight"

def leave_flight(flight_id, user_id, mission_id=None):
    """Leave a flight"""
    flight = get_flight(flight_id, mission_id)
    if not flight:
        return None, "Flight not found"
    
    # Check if user is in flight
    pilot_index = None
    for i, pilot in enumerate(flight.pilots):
        if pilot["user_id"] == user_id:
            pilot_index = i
            break
    
    if pilot_index is None:
        return None, "You are not in this flight"
    
    # Remove pilot from flight
    flight.pilots.pop(pilot_index)
    
    # If flight is now empty, delete it
    if not flight.pilots:
        delete_flight(flight_id, flight.mission_id)
        return None, "Flight deleted - no pilots remaining"
    
    # If flight lead left, promote next pilot to lead
    if pilot_index == 0 and flight.pilots:
        # Update the first pilot's position to "1"
        flight.pilots[0]["position"] = "1"
    
    # Save flight
    save_flight(flight)
    return flight, "Successfully left flight"

def delete_flight(flight_id, mission_id=None):
    """Delete a flight"""
    from utils.storage import load_mission, save_mission
    
    # First try to find the flight
    flight = get_flight(flight_id, mission_id)
    if not flight:
        return False
    
    # If we know the mission_id, we can delete directly
    if mission_id:
        mission = load_mission(mission_id)
        if mission and "flights" in mission and flight_id in mission["flights"]:
            del mission["flights"][flight_id]
            save_mission(mission)
            return True
    else:
        # Otherwise, need to find which mission has this flight
        mission_id = flight.mission_id
        mission = load_mission(mission_id)
        if mission and "flights" in mission and flight_id in mission["flights"]:
            del mission["flights"][flight_id]
            save_mission(mission)
            return True
    
    return False
