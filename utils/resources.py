"""
Utilities for managing resources like callsigns, frequencies, etc.
"""
import os
import json
import random
from utils.storage import load_json, save_json, load_mission, save_mission
from utils.cache import get_cached_json
import logging

logger = logging.getLogger(__name__)

def load_resources():
    """Load resource files from config directory with caching for performance"""
    resources = {}
    # Use instance/data directory for resources
    config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance/data")
    
    resource_files = {
        "squadrons": "squadron_templates/squadron_templates.json",
        # bases.json moved to instance/data/base_locations.json
        # aircraft.json has been superseded by squadron template system
        "frequencies": "freq_ranges.json",
        "operations_areas": "operations_areas.json",  # Will be expanded by get_operations_areas()
        "tacan_channels": "tacan_channels.json"
    }
    
    for resource_name, filename in resource_files.items():
        try:
            resource_path = os.path.join(config_dir, filename)
            # Use cached loading for 50-100x performance improvement
            resources[resource_name] = get_cached_json(resource_path)
            logger.debug(f"Loaded resource {resource_name} from {resource_path} (cached)")
        except FileNotFoundError:
            logger.warning(f"Resource file {filename} not found, creating empty resource")
            resources[resource_name] = {}
            # Do not try to create config_dir or save files if missing, just skip or log
    
    # Check for theater files to ensure they're loaded during resource initialization
    theaters_dir = os.path.join(config_dir, "theatres")
    if os.path.exists(theaters_dir) and os.path.isdir(theaters_dir):
        logger.debug(f"Found theaters directory at {theaters_dir}")
        resources["theaters"] = {}
        for filename in os.listdir(theaters_dir):
            if filename.endswith('.json'):
                theater_path = os.path.join(theaters_dir, filename)
                try:
                    # Just initialize the cache, but don't store in resources yet
                    _ = get_cached_json(theater_path)
                    theater_id = filename.replace('.json', '')
                    resources["theaters"][theater_id] = theater_path
                    logger.debug(f"Initialized theater cache for {filename}")
                except Exception as e:
                    logger.error(f"Failed to initialize theater file {filename}: {e}")
    
    return resources

# Global resources cache with automatic invalidation
_resources = None
_last_check_time = 0
_check_interval = 60  # Check for file changes every 60 seconds

def get_resources():
    """Get resources, loading from disk if necessary or cache is stale"""
    global _resources, _last_check_time
    import time
    
    current_time = time.time()
    
    # Force reload if cache is None or enough time has passed
    if _resources is None or (current_time - _last_check_time) > _check_interval:
        _resources = load_resources()
        _last_check_time = current_time
        logger.debug("Resources cache refreshed")
    
    return _resources

def invalidate_resources_cache():
    """Manually invalidate the resources cache (call after config changes)"""
    global _resources, _last_check_time
    _resources = None
    _last_check_time = 0
    logger.info("Resources cache manually invalidated")

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

def get_callsign(squadron_id, campaign_id=None):
    """Get a callsign for a squadron, using campaign's squadrons.json if campaign_id is provided."""
    import logging
    logger = logging.getLogger(__name__)
    if campaign_id:
        try:
            # Load campaign squadrons.json
            campaign_sq_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                f"instance/campaigns/{campaign_id}/squadrons.json"
            )
            with open(campaign_sq_path, 'r') as f:
                campaign_squadrons = json.load(f)
            sq = campaign_squadrons.get(squadron_id)
            if sq:
                callsigns = sq.get('callsigns', [])
                if isinstance(callsigns, list) and callsigns:
                    logger.debug(f"[get_callsign] Using campaign {campaign_id} squadrons.json for {squadron_id}, callsigns: {callsigns}")
                    return random.choice(callsigns)
                else:
                    logger.warning(f"[get_callsign] No callsigns defined for squadron {squadron_id} in campaign {campaign_id}")
            else:
                logger.warning(f"[get_callsign] Squadron {squadron_id} not found in campaign {campaign_id} squadrons.json")
        except Exception as e:
            logger.warning(f"[get_callsign] Failed to get callsign from campaign {campaign_id} for {squadron_id}: {e}")
        # If campaign_id is provided but not found, do NOT fall back to template (enforced)
        return squadron_id
    # Fallback to legacy resources
    resources = get_resources()
    squadron_data = resources["squadrons"].get(squadron_id, {})
    callsigns = squadron_data.get("callsigns", [squadron_id])
    if isinstance(callsigns, list) and callsigns:
        return random.choice(callsigns)
    return squadron_id

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

def get_aircraft_at_base(base_id, campaign_id=None):
    """Get available aircraft at a specific base (uses 'location' field)
    
    Args:
        base_id: Base identifier
        campaign_id: Optional campaign ID for campaign-specific aircraft state
    """
    if campaign_id:
        # Use campaign-specific aircraft state
        try:
            from utils.aircraft_state import get_aircraft_at_base_for_campaign
            return get_aircraft_at_base_for_campaign(campaign_id, base_id)
        except Exception as e:
            logger.warning(f"Failed to get campaign aircraft state for {campaign_id}: {e}")
    
    # Fallback to legacy resources
    resources = get_resources()
    all_aircraft = resources.get("aircraft", {})
    # Use 'location' instead of 'base' for matching
    aircraft_at_base = {
        ac_id: ac_data for ac_id, ac_data in all_aircraft.items()
        if ac_data.get("location") == base_id
    }
    return aircraft_at_base

def get_squadron_aircraft(squadron_id, base_id=None, campaign_id=None):
    """Get aircraft for a squadron, optionally filtered by base, using campaign's squadrons.json if campaign_id is provided."""
    import logging
    logger = logging.getLogger(__name__)
    if not campaign_id:
        raise RuntimeError("[get_squadron_aircraft] campaign_id is required; fallback to template/legacy is not allowed.")
    try:
        # Load campaign squadrons.json
        campaign_sq_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            f"instance/campaigns/{campaign_id}/squadrons.json"
        )
        with open(campaign_sq_path, 'r') as f:
            campaign_squadrons = json.load(f)
        # Support both flat and nested ("squadrons": {...}) formats
        if 'squadrons' in campaign_squadrons:
            campaign_squadrons = campaign_squadrons['squadrons']
        sq = campaign_squadrons.get(squadron_id)
        if not sq:
            raise RuntimeError(f"[get_squadron_aircraft] Squadron {squadron_id} not found in campaign {campaign_id}")
        aircraft_list = sq.get('aircraft', [])
        aircraft_type = sq.get('aircraft_type', 'UNKNOWN')
        # Each aircraft is a dict with at least 'tail', 'location', and 'state'
        aircraft = {}
        for ac in aircraft_list:
            if not isinstance(ac, dict):
                continue
            if base_id and ac.get('location') != base_id:
                continue
            tail = ac.get('tail')
            if not tail:
                continue
            aircraft[tail] = {
                'tail': tail,
                'type': aircraft_type,
                'squadron': squadron_id,
                'location': ac.get('location'),
                'state': ac.get('state', 100)
            }
        logger.debug(f"[get_squadron_aircraft] Using campaign {campaign_id} squadrons.json for {squadron_id}, found {len(aircraft)} aircraft")
        return aircraft
    except Exception as e:
        logger.error(f"[get_squadron_aircraft] Failed to get aircraft from campaign {campaign_id} for {squadron_id}: {e}")
        raise RuntimeError(f"[get_squadron_aircraft] Error: {e}")

def get_bases(campaign_id=None):
    """Get all bases for the campaign's theatre (from theatre file). Strict: campaign_id is required, no fallback."""
    import logging
    logger = logging.getLogger(__name__)
    if not campaign_id:
        logger.error("[get_bases] campaign_id is required but was not provided.")
        raise RuntimeError("[get_bases] campaign_id is required.")
    try:
        # Load the campaign's theatre from the campaign.json
        campaign_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            f"instance/campaigns/{campaign_id}/campaign.json"
        )
        with open(campaign_path, 'r') as f:
            campaign_data = json.load(f)
        theatre_id = campaign_data.get('theatre')
        if not theatre_id:
            logger.error(f"[get_bases] No theatre set in campaign.json for {campaign_id}")
            raise RuntimeError(f"[get_bases] No theatre set in campaign.json for {campaign_id}")
        # Remove .json extension if present
        if theatre_id.lower().endswith('.json'):
            theatre_id = theatre_id[:-5]
        # Load the theatre file
        theatre_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            f"instance/data/theatres/{theatre_id.lower()}.json"
        )
        with open(theatre_path, 'r') as f:
            theatre_data = json.load(f)
        bases = {b['id']: b for b in theatre_data.get('bases', [])}
        logger.debug(f"[get_bases] Loaded {len(bases)} bases from theatre {theatre_id} for campaign {campaign_id}")
        return bases
    except Exception as e:
        logger.error(f"[get_bases] Failed to load bases for campaign {campaign_id}: {e}")
        raise RuntimeError(f"[get_bases] Error loading bases for campaign {campaign_id}: {e}")


def get_operations_areas():
    """Get all operations areas from theater-specific files"""
    resources = get_resources()
    operations_areas = resources.get("operations_areas", {})
    
    # Check if we need to load from theater files
    if not operations_areas or "note" in operations_areas:
        # Load from theater-specific files
        config_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "instance/data")
        theaters_dir = os.path.join(config_dir, "theatres")
        
        # Initialize empty operations areas dict
        operations_areas = {}
        
        # Check if theaters directory exists
        if os.path.exists(theaters_dir) and os.path.isdir(theaters_dir):
            # Iterate through all theater files
            for filename in os.listdir(theaters_dir):
                if filename.endswith('.json'):
                    theater_path = os.path.join(theaters_dir, filename)
                    try:
                        # Load theater file
                        theater_data = get_cached_json(theater_path)
                        theater_name = theater_data.get('name', filename.replace('.json', ''))
                        
                        # Extract training areas
                        if 'training_areas' in theater_data:
                            for area in theater_data['training_areas']:
                                area_id = f"{theater_name.upper()}_{area['name'].replace(' ', '_')}"
                                operations_areas[area_id] = {
                                    'name': f"{theater_name} - {area['name']}",
                                    'description': area.get('description', ''),
                                    'theater': theater_name
                                }
                        logger.debug(f"Loaded operations areas from theater file: {filename}")
                    except Exception as e:
                        logger.error(f"Failed to load theater file {filename}: {e}")
        
    return operations_areas

def get_squadrons(campaign_id=None):
    """Get all squadrons, using campaign's squadrons.json if campaign_id is provided."""
    import logging
    logger = logging.getLogger(__name__)
    if not campaign_id:
        raise RuntimeError("[get_squadrons] campaign_id is required; fallback to template/legacy is not allowed.")
    try:
        campaign_sq_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            f"instance/campaigns/{campaign_id}/squadrons.json"
        )
        with open(campaign_sq_path, 'r') as f:
            campaign_squadrons = json.load(f)
        # Support both flat and nested ("squadrons": {...}) formats
        if 'squadrons' in campaign_squadrons:
            campaign_squadrons = campaign_squadrons['squadrons']
        logger.debug(f"[get_squadrons] Using campaign {campaign_id} squadrons.json, found {len(campaign_squadrons)} squadrons")
        return campaign_squadrons
    except Exception as e:
        logger.error(f"[get_squadrons] Failed to load campaign squadrons.json for {campaign_id}: {e}")
        raise RuntimeError(f"[get_squadrons] Error: {e}")
