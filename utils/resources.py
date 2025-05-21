"""
Utilities for managing resources like callsigns, frequencies, etc.
"""
import os
import json
import random
from utils.storage import load_json, save_json, load_mission, save_mission
import logging

logger = logging.getLogger(__name__)

def load_resources():
    """Load resource files from config directory"""
    resources = {}
    # Use project-level config directory instead of instance/config
    config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config")
    
    resource_files = {
        "squadrons": "squadrons.json",
        "bases": "bases.json",
        "aircraft": "aircraft.json",
        "frequencies": "frequencies.json",
        "operations_areas": "operations_areas.json",
        "tacan_channels": "tacan_channels.json"
    }
    
    for resource_name, filename in resource_files.items():
        try:
            resource_path = os.path.join(config_dir, filename)
            resources[resource_name] = load_json(resource_path)
        except FileNotFoundError:
            logger.warning(f"Resource file {filename} not found, creating empty resource")
            resources[resource_name] = {}
            # Do not try to create config_dir or save files if missing, just skip or log
    
    return resources

# Global resources cache
_resources = None

def get_resources():
    """Get resources, loading from disk if necessary"""
    global _resources
    if _resources is None:
        _resources = load_resources()
    return _resources

def get_mission_resource_usage(mission_id):
    """Get or initialize resource usage for a mission (stored inside the mission JSON)."""
    mission = load_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission {mission_id} not found")
    # Initialize resources if not present
    if 'resources' not in mission:
        mission['resources'] = {
            "flight_numbers": {},  # By squadron
            "transponder_codes": [],
            "tacan_channels": [],
            "frequencies": []
        }
        save_mission(mission)
    return mission['resources']

def save_mission_resource_usage(mission_id, resource_usage):
    """Save resource usage for a mission (inside the mission JSON)."""
    mission = load_mission(mission_id)
    if mission is None:
        raise ValueError(f"Mission {mission_id} not found")
    mission['resources'] = resource_usage
    save_mission(mission)

def get_next_flight_number(mission_id, squadron):
    """Get the next flight number for a squadron"""
    resources = get_mission_resource_usage(mission_id)
    
    # If squadron doesn't exist in flight numbers, add it
    if squadron not in resources["flight_numbers"]:
        resources["flight_numbers"][squadron] = 0
    
    # Increment flight number
    resources["flight_numbers"][squadron] += 1
    
    # Save updated resources
    save_mission_resource_usage(mission_id, resources)
    
    return resources["flight_numbers"][squadron]

def get_callsign(squadron):
    """Get a callsign from the squadron's callsign bank"""
    resources = get_resources()
    
    # Get squadron data
    squadron_data = resources["squadrons"].get(squadron, {})
    callsigns = squadron_data.get("callsigns", ["UNKNOWN"])
    
    # Return a random callsign from the bank
    return random.choice(callsigns)

def get_transponder_codes(mission_id, count=4):
    """Get a bank of unique transponder codes"""
    resources = get_mission_resource_usage(mission_id)
    all_resources = get_resources()
    
    # Get available transponder codes
    available_codes = all_resources.get("frequencies", {}).get("transponder", [])
    used_codes = resources["transponder_codes"]
    
    # Filter out used codes
    available_codes = [code for code in available_codes if code not in used_codes]
    
    # If we don't have enough available codes, generate random ones
    if len(available_codes) < count:
        available_codes.extend([f"{random.randint(0, 7)}{random.randint(0, 7)}{random.randint(0, 7)}{random.randint(0, 7)}" 
                              for _ in range(count - len(available_codes))])
    
    # Select 'count' codes
    selected_codes = random.sample(available_codes, count)
    
    # Update used codes
    resources["transponder_codes"].extend(selected_codes)
    save_mission_resource_usage(mission_id, resources)
    
    return selected_codes

def get_tacan_channel(mission_id):
    """Get a unique TACAN channel"""
    resources = get_mission_resource_usage(mission_id)
    all_resources = get_resources()
    
    # Get available TACAN channels
    available_channels = all_resources.get("tacan_channels", [])
    used_channels = resources["tacan_channels"]
    
    # Filter out used channels
    available_channels = [ch for ch in available_channels if ch not in used_channels]
    
    # If no channels are available, generate a random one
    if not available_channels:
        # Format: 2-digit number (1-126) + X/Y
        channel = f"{random.randint(1, 126)}{random.choice(['X', 'Y'])}"
    else:
        channel = random.choice(available_channels)
    
    # Update used channels
    resources["tacan_channels"].append(channel)
    save_mission_resource_usage(mission_id, resources)
    
    return channel

def get_intraflight_freq(mission_id):
    """Get a unique intraflight frequency"""
    resources = get_mission_resource_usage(mission_id)
    all_resources = get_resources()
    
    # Get available frequencies
    available_freqs = all_resources.get("frequencies", {}).get("intraflight", [])
    used_freqs = resources["frequencies"]
    
    # Filter out used frequencies
    available_freqs = [freq for freq in available_freqs if freq not in used_freqs]
    
    # If no frequencies are available, generate a random one
    if not available_freqs:
        # Format: VHF frequency in format 1xx.xx
        freq = f"1{random.randint(0, 9)}{random.randint(0, 9)}.{random.randint(0, 9)}{random.randint(0, 5)}"
    else:
        freq = random.choice(available_freqs)
    
    # Update used frequencies
    resources["frequencies"].append(freq)
    save_mission_resource_usage(mission_id, resources)
    
    return freq

def get_aircraft_at_base(base_id):
    """Get available aircraft at a specific base (uses 'location' field)"""
    resources = get_resources()
    all_aircraft = resources.get("aircraft", {})
    # Use 'location' instead of 'base' for matching
    aircraft_at_base = {
        ac_id: ac_data for ac_id, ac_data in all_aircraft.items()
        if ac_data.get("location") == base_id
    }
    return aircraft_at_base

def get_bases():
    """Get all bases"""
    resources = get_resources()
    return resources.get("bases", {})

def get_operations_areas():
    """Get all operations areas"""
    resources = get_resources()
    return resources.get("operations_areas", {})

def get_squadrons():
    """Get all squadrons"""
    resources = get_resources()
    return resources.get("squadrons", {})
