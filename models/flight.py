"""
Flight model for the signup module
"""
import json
import os
import traceback
import uuid
from datetime import datetime
import logging
from pathlib import Path

# Import utils once at the top level
from utils.storage import load_json, save_json, load_mission, save_mission, list_missions
from utils.resources import (
    get_squadrons, get_tacan_channel, get_intraflight_freq, 
    get_aircraft_at_base, get_squadron_aircraft
)
from utils.squadron_manager import squadron_manager

logger = logging.getLogger(__name__)

def convert_old_flight_data(flight_data, mission_id):
    """
    Convert old format flight data to new format.
    
    Args:
        flight_data (dict): Flight data in old or new format
        mission_id (str): The mission ID this flight belongs to
        
    Returns:
        dict: Flight data in the new format
    """
    # Skip conversion if already in new format
    if "flight_id" in flight_data and "mission_id" in flight_data:
        return flight_data
    
    # Skip if missing critical data
    if "id" not in flight_data:
        logger.warning(f"Skipping flight data with missing ID: {flight_data.keys()}")
        return flight_data
    
    # Convert members list to pilots list with proper structure
    pilots = []
    if "members" in flight_data:
        for i, member_username in enumerate(flight_data["members"]):
            # For old data, we don't have user_ids, so we'll use username as fallback
            pilot = {
                "user_id": member_username,  # We don't have actual user_id in old data
                "username": member_username,
                "nickname": member_username,
                "position": str(i + 1),  # Assign positions 1, 2, 3, etc.
                "joined_at": flight_data.get("created_at", ""),
                "callsign": f"{flight_data['callsign']}{flight_data.get('flight_number', 1)}{i + 1}",
                "transponder": None,  # Old data doesn't have individual transponders
                "aircraft": flight_data.get("aircraft_id")
            }
            pilots.append(pilot)
    
    # Build the standardized flight data dictionary
    return {
        "mission_id": mission_id,
        "flight_id": flight_data["id"],
        "squadron": flight_data.get("squadrons", ["unknown"])[0] if flight_data.get("squadrons") else "unknown",
        "callsign": flight_data["callsign"],
        "flight_number": flight_data.get("flight_number", 1),
        "departure_base": flight_data["departure_base"],
        "recovery_base": flight_data["recovery_base"],
        "operations_area": flight_data["operations_area"],
        "mission_type": flight_data.get("role"),
        "remarks": flight_data.get("remarks", ""),
        "aircraft_ids": [flight_data["aircraft_id"]] if flight_data.get("aircraft_id") else [],
        "transponder_codes": flight_data.get("transponder_codes", []),
        "tacan_channel": flight_data.get("tacan_channel"),
        "intraflight_freq": flight_data.get("intraflight_freq"),
        "pilots": pilots,
        "status": flight_data.get("status", "active"),
        "side": flight_data.get("side", "blue"),
        "created_at": flight_data.get("created_at", datetime.now().isoformat())
    }


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
    """
    Create a new flight in a mission.
    All squadron/callsign/aircraft data must come from the campaign's squadrons.json, NOT the squadron template.
    """
    logger.debug(f"[CREATE_FLIGHT] mission_id={mission_id}, flight_data={flight_data}, user_id={user_id}, username={username}")
    try:
        mission = load_mission(mission_id)
        if not mission:
            logger.error(f"Mission {mission_id} not found")
            raise ValueError(f"Mission {mission_id} not found")
        campaign_id = mission.get("campaign_id")
        if not campaign_id:
            raise ValueError("Mission missing campaign_id")
        # Load campaign squadrons.json (dict keyed by squadron ID)
        import os
        from utils.storage import load_json
        campaign_dir = os.path.join(os.path.dirname(__file__), '../instance/campaigns', campaign_id)
        squadrons_path = os.path.join(campaign_dir, 'squadrons.json')
        campaign_squadrons = load_json(squadrons_path).get('squadrons', {})
        squadron_id = flight_data["squadron"]
        squadron_info = campaign_squadrons.get(squadron_id)
        if not squadron_info:
            raise ValueError(f"Squadron {squadron_id} not found in campaign squadrons.json")
        # Use campaign-specific callsigns
        callsign_bank = squadron_info.get('callsigns', [squadron_id])
        # Find all used callsigns and flight_numbers
        used_callsigns = set()
        used_numbers = set()
        if "flights" in mission:
            for f in mission["flights"].values():
                if f["squadron"] == squadron_id:
                    used_callsigns.add(f["callsign"])
                    used_numbers.add(f["flight_number"])
        # Find an available callsign and flight number
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
        import json
        mission_types_path = os.path.join(os.path.dirname(__file__), '../config/mission_types.json')
        with open(mission_types_path) as f:
            mission_types = json.load(f)
        prefix = mission_types.get(mission_type, {}).get("transponder", "00")
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
            pilots=[{
                "user_id": user_id, 
                "username": username, 
                "nickname": username,  # display_name is passed as username
                "position": "1", 
                "joined_at": datetime.now().isoformat(), 
                "callsign": pilot_callsign, 
                "transponder": pilot_transponder, 
                "squawk": pilot_transponder,  # for template compatibility
                "aircraft": aircraft_id,
                "aircraft_id": aircraft_id  # for template compatibility
            }],
            side=flight_data.get("side", "blue")
        )
        logger.debug(f"[CREATE_FLIGHT] Flight object created: {flight.to_dict()}")
        # Add flight to mission
        if "flights" not in mission:
            mission["flights"] = {}
        mission["flights"][flight.flight_id] = flight.to_dict()
        # Save the mission
        save_mission(mission)
        logger.info(f"[CREATE_FLIGHT] Flight {flight.flight_id} created and saved successfully.")
        return flight
    except Exception as e:
        logger.error(f"[CREATE_FLIGHT] Exception: {e}\n{traceback.format_exc()}")
        raise

def save_flight(flight):
    """
    Save a flight to the mission's flight list
    
    Args:
        flight (Flight): The flight object to save
        
    Returns:
        bool: True if save was successful, False otherwise
    """
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
    """
    Get a flight by ID
    
    Args:
        flight_id (str): The flight ID to retrieve
        mission_id (str, optional): The mission ID to search in. Defaults to None (search all missions).
        
    Returns:
        Flight: The flight object if found, None otherwise
    """
    logger.debug(f"[get_flight] Searching for flight_id={flight_id} in mission_id={mission_id}")
    
    # If mission_id is provided, check only that mission
    if mission_id:
        mission = load_mission(mission_id)
        if mission and "flights" in mission:
            logger.debug(f"[get_flight] Available flight IDs in mission: {list(mission['flights'].keys())}")
            if flight_id in mission["flights"]:
                flight_data = convert_old_flight_data(mission["flights"][flight_id], mission_id)
                return Flight.from_dict(flight_data)
        return None
        
    # Otherwise, check all missions
    missions = list_missions()
    for current_mission_id in missions:
        mission = load_mission(current_mission_id)
        if mission and "flights" in mission:
            logger.debug(f"[get_flight] Available flight IDs in mission {current_mission_id}: {list(mission['flights'].keys())}")
            if flight_id in mission["flights"]:
                flight_data = convert_old_flight_data(mission["flights"][flight_id], current_mission_id)
                return Flight.from_dict(flight_data)
                
    logger.error(f"[get_flight] Flight {flight_id} not found in any mission")
    return None

def get_mission_flights(mission_id):
    """
    Get all flight IDs for a mission
    
    Args:
        mission_id (str): The mission ID to get flights for
        
    Returns:
        list: List of flight IDs in the mission
    """
    mission = load_mission(mission_id)
    if not mission or "flights" not in mission:
        return []
    
    return list(mission["flights"].keys())


def get_mission_flights_data(mission_id):
    """
    Get all flight data for a mission
    
    Args:
        mission_id (str): The mission ID to get flight data for
        
    Returns:
        list: List of Flight objects in the mission
    """
    mission = load_mission(mission_id)
    if not mission or "flights" not in mission:
        return []
    
    flights = []
    for flight_data in mission["flights"].values():
        # Convert data to the standardized format
        converted_data = convert_old_flight_data(flight_data, mission_id)
        flights.append(Flight.from_dict(converted_data))
    
    return flights

def join_flight(flight_id, user_id, username, position, mission_id=None, aircraft=None):
    """
    Join a flight at the specified position, with selected aircraft
    
    Args:
        flight_id (str): The flight ID to join
        user_id (str): User ID of the pilot joining
        username (str): Username of the pilot joining
        position (str): Position number in the flight (1-4)
        mission_id (str, optional): Mission ID to narrow search. Defaults to None.
        aircraft (str, optional): Aircraft ID to use. Defaults to None.
        
    Returns:
        tuple: (Flight object if successful, message string)
    """
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
    pilot_callsign = f"{flight.callsign}{flight.flight_number}{position}"
    pilot_transponder = None
    try:
        pos_num = int(position)
    except ValueError:
        pos_num = 0
    if flight.transponder_codes and 1 <= pos_num <= len(flight.transponder_codes):
        pilot_transponder = flight.transponder_codes[pos_num-1]
    flight.pilots.append({
        "user_id": user_id,
        "username": username,
        "nickname": username,  # display_name is passed as username
        "position": position,
        "joined_at": datetime.now().isoformat(),
        "callsign": pilot_callsign,
        "transponder": pilot_transponder,
        "squawk": pilot_transponder,  # for template compatibility
        "aircraft": aircraft,
        "aircraft_id": aircraft  # for template compatibility
    })

    # Save changes to flight
    save_flight(flight)
    return flight, "Successfully joined flight"

def leave_flight(flight_id, user_id, mission_id=None):
    """
    Leave a flight
    
    Args:
        flight_id (str): The flight ID to leave
        user_id (str): User ID of the pilot leaving
        mission_id (str, optional): Mission ID to narrow search. Defaults to None.
        
    Returns:
        tuple: (Flight object if still exists, message string)
    """
    flight = get_flight(flight_id, mission_id)
    if not flight:
        return None, "Flight not found"
    
    # Check if user is in flight
    pilot_index = None
    for i, pilot in enumerate(flight.pilots):
        if str(pilot["user_id"]) == str(user_id):
            pilot_index = i
            break
    
    if pilot_index is None:
        return None, "You are not in this flight"
    
    # Remove pilot from flight
    flight.pilots.pop(pilot_index)

    # If flight is now empty, delete it and restore curated slot if needed
    if not flight.pilots:
        logger.info(f"[LEAVE_FLIGHT] Flight {flight_id} is now empty. Checking for curated slot restoration...")
        mission = load_mission(flight.mission_id)
        restored = False
        if mission and 'curated_slots' in mission:
            slot_idx = None
            if hasattr(flight, 'claimed_from_slot'):
                slot_idx = getattr(flight, 'claimed_from_slot', None)
            elif hasattr(flight, 'to_dict') and 'claimed_from_slot' in flight.to_dict():
                slot_idx = flight.to_dict().get('claimed_from_slot')
            if slot_idx is not None and 'original_curated_slots' in mission:
                try:
                    slot_data = mission['original_curated_slots'][slot_idx]
                    # If using squadron callsigns, clear label
                    if slot_data.get('useSquadronCallsigns'):
                        slot_data = dict(slot_data)
                        slot_data['label'] = ''
                    mission['curated_slots'].append(slot_data)
                    logger.info(f"[LEAVE_FLIGHT] Restored curated slot from original_curated_slots idx {slot_idx} for flight {flight_id}")
                    restored = True
                except Exception as e:
                    logger.warning(f"[LEAVE_FLIGHT] Could not restore curated slot from original_curated_slots: {e}")
            if not restored:
                # Fallback: reconstruct slot from flight data
                slot_data = {
                    'label': '' if getattr(flight, 'useSquadronCallsigns', True) else (flight.callsign or 'UNKNOWN'),
                    'role': flight.mission_type or '',
                    'squadrons': [flight.squadron] if flight.squadron else [],
                    'seats': len(flight.aircraft_ids) if flight.aircraft_ids else 1,
                    'description': flight.remarks or '',
                    'useSquadronCallsigns': True
                }
                mission['curated_slots'].append(slot_data)
                logger.info(f"[LEAVE_FLIGHT] Fallback: Reconstructed and restored curated slot for flight {flight_id}")
            save_mission(mission)
        delete_flight(flight_id, flight.mission_id)
        return None, "Flight deleted - no pilots remaining (curated slot restored if applicable)"
    
    # If flight lead left, promote next pilot to lead
    if pilot_index == 0 and flight.pilots:
        # Update the first pilot's position to "1"
        flight.pilots[0]["position"] = "1"
    
    # Save flight
    save_flight(flight)
    return flight, "Successfully left flight"

def delete_flight(flight_id, mission_id=None):
    """
    Delete a flight
    
    Args:
        flight_id (str): The flight ID to delete
        mission_id (str, optional): Mission ID to narrow search. Defaults to None.
        
    Returns:
        bool: True if deletion was successful, False otherwise
    """
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
        # Otherwise, use the mission_id from the flight object
        mission_id = flight.mission_id
        mission = load_mission(mission_id)
        if mission and "flights" in mission and flight_id in mission["flights"]:
            del mission["flights"][flight_id]
            save_mission(mission)
            return True
    
    return False
