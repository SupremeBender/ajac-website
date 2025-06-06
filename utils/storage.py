import os
import json
from pathlib import Path
import uuid
from datetime import datetime
from flask import current_app
from utils.cache import get_cached_json

def ensure_data_dirs():
    """Ensure all data directories exist"""
    data_dir = Path(current_app.instance_path) / "missions"
    data_dir.mkdir(exist_ok=True)
    return data_dir

def ensure_campaign_data_dir():
    """Ensure campaign data directory exists"""
    data_dir = Path(current_app.instance_path) / "campaigns"
    data_dir.mkdir(exist_ok=True)
    return data_dir

def ensure_campaign_dir(campaign_id):
    """Ensure specific campaign directory exists"""
    campaigns_dir = ensure_campaign_data_dir()
    campaign_dir = campaigns_dir / campaign_id
    campaign_dir.mkdir(exist_ok=True)
    (campaign_dir / "missions").mkdir(exist_ok=True)
    (campaign_dir / "resources").mkdir(exist_ok=True)
    return campaign_dir

def get_campaign_dir(campaign_id):
    """Get campaign directory path without ensuring it exists
    
    Args:
        campaign_id: Campaign ID
        
    Returns:
        Path object for the campaign directory
    """
    campaigns_dir = Path(current_app.instance_path) / "campaigns"
    return campaigns_dir / campaign_id

def generate_mission_id(operation_code, mission_type, sequence_number=None, campaign_id=None):
    """Generate a mission ID following ATO conventions.
    Args:
        operation_code: Shorthand code for the operation (e.g., "PP15")
        mission_type: EX for exercise, OP for operation (from campaign)
        sequence_number: Sequence number within the operation (auto-incremented)
        campaign_id: Campaign ID to search for existing missions (for sequence generation)
    Format: [OPERATION_CODE] | [EX/OP][SEQUENCE]
    Examples: PP15 | EX01, RF22 | OP03
    """
    if not operation_code:
        raise ValueError("Operation code is required (from campaign shorthand)")
    operation_code = operation_code.strip().upper()
    mission_type = mission_type.upper() if mission_type.upper() in ["EX", "OP"] else "EX"
    
    if not sequence_number:
        highest_seq = 0
        
        if campaign_id:
            # Search in campaign-specific missions directory
            campaigns_dir = ensure_campaign_data_dir()
            missions_dir = campaigns_dir / campaign_id / "missions"
            if missions_dir.exists():
                pattern = f"{operation_code}{mission_type}*.json"
                existing_missions = list(missions_dir.glob(pattern))
                for mission_path in existing_missions:
                    try:
                        fname = mission_path.stem  # e.g., PP15EX01
                        if fname.startswith(operation_code + mission_type):
                            seq_part = fname[len(operation_code + mission_type):]
                            seq = int(seq_part)
                            highest_seq = max(highest_seq, seq)
                    except (ValueError, IndexError):
                        continue
        else:
            # Search across all campaigns for highest sequence (fallback)
            campaigns_dir = ensure_campaign_data_dir()
            for campaign_folder in campaigns_dir.iterdir():
                if campaign_folder.is_dir():
                    missions_dir = campaign_folder / "missions"
                    if missions_dir.exists():
                        pattern = f"{operation_code}{mission_type}*.json"
                        existing_missions = list(missions_dir.glob(pattern))
                        for mission_path in existing_missions:
                            try:
                                fname = mission_path.stem  # e.g., PP15EX01
                                if fname.startswith(operation_code + mission_type):
                                    seq_part = fname[len(operation_code + mission_type):]
                                    seq = int(seq_part)
                                    highest_seq = max(highest_seq, seq)
                            except (ValueError, IndexError):
                                continue
        
        sequence_number = highest_seq + 1
    
    seq_formatted = f"{int(sequence_number):02d}"
    mission_id = f"{operation_code} | {mission_type}{seq_formatted}"
    return mission_id

def mission_id_to_filename(mission_id):
    """Convert mission ID to a simple, safe filename (e.g., PP15EX01.json)"""
    # Remove all non-alphanumeric characters
    return ''.join(c for c in mission_id if c.isalnum()) + ".json"

def campaign_id_to_filename(campaign_id):
    """Convert campaign ID to a simple, safe filename (e.g., PP15.json)"""
    return ''.join(c for c in campaign_id if c.isalnum()) + ".json"

def save_mission(mission_data):
    """Save mission to campaign-specific missions folder"""
    campaign_id = mission_data.get("campaign_id")
    if not campaign_id:
        raise ValueError("Mission must have a campaign_id to determine save location")
    
    # Ensure campaign missions directory exists
    campaign_dir = ensure_campaign_data_dir() / campaign_id
    missions_dir = campaign_dir / "missions"
    missions_dir.mkdir(parents=True, exist_ok=True)
    
    mission_id = mission_data.get("id")
    if not mission_id:
        # Get campaign data to determine operation code and mission type
        campaign_data = load_campaign(campaign_id)
        operation_code = campaign_data.get("shorthand", "") if campaign_data else ""
        mission_type = campaign_data.get("type", "EX") if campaign_data else "EX"
        mission_id = generate_mission_id(operation_code, mission_type, campaign_id=campaign_id)
        mission_data["id"] = mission_id
    
    file_path = missions_dir / mission_id_to_filename(mission_id)
    
    with open(file_path, 'w') as f:
        json.dump(mission_data, f, indent=4)
    
    return mission_id

def save_campaign(campaign_data):
    """Save campaign data to hierarchical campaign structure"""
    campaign_id = campaign_data.get("id")
    if not campaign_id:
        # Use shorthand as ID
        campaign_id = campaign_data.get("shorthand", str(uuid.uuid4()))
        campaign_data["id"] = campaign_id
    
    # Ensure campaign directory structure exists
    campaign_dir = ensure_campaign_dir(campaign_id)
    
    # Extract squadron data from campaign_data
    squadrons_data = campaign_data.pop("squadrons", [])
    
    # Save campaign metadata
    campaign_file = campaign_dir / "campaign.json"
    with open(campaign_file, 'w') as f:
        json.dump(campaign_data, f, indent=4)
    
    # Save squadrons data (NEW FORMAT: dict keyed by squadron ID)
    squadrons_file = campaign_dir / "squadrons.json"
    with open(squadrons_file, 'w') as f:
        json.dump({"squadrons": squadrons_data}, f, indent=4)
    
    return campaign_id

def load_mission(mission_id, campaign_id=None):
    """Load a mission by its simplified ID (e.g. PP15EX01). Always set mission['id'] and mission['name'].
    Args:
        mission_id: The mission ID to load
        campaign_id: Optional campaign ID to search within specific campaign
    """
    filename = mission_id_to_filename(mission_id)
    
    if campaign_id:
        # Search in specific campaign
        campaigns_dir = ensure_campaign_data_dir()
        missions_dir = campaigns_dir / campaign_id / "missions"
        file_path = missions_dir / filename
        if file_path.exists():
            with open(file_path, 'r', encoding='utf-8') as f:
                mission = json.load(f)
            mission['id'] = mission_id
            mission['name'] = mission.get('id_raw') or mission.get('name') or mission.get('id')
            if 'id_raw' in mission:
                del mission['id_raw']
            return mission
    
    # Search across all campaigns
    campaigns_dir = ensure_campaign_data_dir()
    for campaign_folder in campaigns_dir.iterdir():
        if campaign_folder.is_dir():
            missions_dir = campaign_folder / "missions"
            file_path = missions_dir / filename
            if file_path.exists():
                with open(file_path, 'r', encoding='utf-8') as f:
                    mission = json.load(f)
                mission['id'] = mission_id
                mission['name'] = mission.get('id_raw') or mission.get('name') or mission.get('id')
                if 'id_raw' in mission:
                    del mission['id_raw']
                return mission
    
    # Fallback to old flat structure for backward compatibility
    data_dir = ensure_data_dirs()
    file_path = data_dir / filename
    if file_path.exists():
        with open(file_path, 'r', encoding='utf-8') as f:
            mission = json.load(f)
        mission['id'] = mission_id
        mission['name'] = mission.get('id_raw') or mission.get('name') or mission.get('id')
        if 'id_raw' in mission:
            del mission['id_raw']
        return mission
    
    return None

def load_campaign(campaign_id):
    """Load campaign data from hierarchical campaign structure"""
    campaigns_dir = ensure_campaign_data_dir()
    campaign_dir = campaigns_dir / campaign_id
    
    # Check if new structure exists
    campaign_file = campaign_dir / "campaign.json"
    squadrons_file = campaign_dir / "squadrons.json"
    
    if campaign_file.exists():
        # Load from new hierarchical structure
        with open(campaign_file, 'r') as f:
            campaign_data = json.load(f)
        
        # Load squadrons if available
        if squadrons_file.exists():
            with open(squadrons_file, 'r') as f:
                squadrons_data = json.load(f)
                campaign_data["squadrons"] = squadrons_data.get("squadrons", [])
        
        return campaign_data
    
    # Fallback to old flat structure for backward compatibility
    old_file_path = campaigns_dir / campaign_id_to_filename(campaign_id)
    if old_file_path.exists():
        with open(old_file_path, 'r') as f:
            return json.load(f)
    
    return None

def list_missions():
    """List all missions from all campaigns, returning a list of dicts with 'id' (PP15EX01) and 'name' (PP15 | EX01)"""
    missions = []
    
    # Search in all campaign directories
    campaigns_dir = ensure_campaign_data_dir()
    for campaign_folder in campaigns_dir.iterdir():
        if campaign_folder.is_dir():
            missions_dir = campaign_folder / "missions"
            if missions_dir.exists():
                for mission_file in missions_dir.glob("*.json"):
                    try:
                        mission_id = mission_file.stem
                        with open(mission_file, 'r', encoding='utf-8') as f:
                            mission = json.load(f)
                        mission['id'] = mission_id
                        mission['name'] = mission.get('id_raw') or mission.get('name') or mission.get('id')
                        if 'id_raw' in mission:
                            del mission['id_raw']
                        missions.append(mission)
                    except (json.JSONDecodeError, IOError):
                        continue
    
    # Also check old flat structure for backward compatibility
    old_missions_dir = Path(current_app.instance_path) / "missions"
    if old_missions_dir.exists():
        for mission_file in old_missions_dir.glob("*.json"):
            try:
                mission_id = mission_file.stem
                # Skip if we already found this mission in new structure
                if any(m['id'] == mission_id for m in missions):
                    continue
                    
                with open(mission_file, 'r', encoding='utf-8') as f:
                    mission = json.load(f)
                mission['id'] = mission_id
                mission['name'] = mission.get('id_raw') or mission.get('name') or mission.get('id')
                if 'id_raw' in mission:
                    del mission['id_raw']
                missions.append(mission)
            except (json.JSONDecodeError, IOError):
                continue
    
    # Sort missions by time_real, handling None values safely
    def safe_time_real(m):
        val = m.get('time_real', '')
        return val if val is not None else ''
    
    missions.sort(key=safe_time_real)
    return missions

def list_campaigns():
    """List all campaigns from both old and new structures"""
    campaigns_dir = ensure_campaign_data_dir()
    campaigns = []
    
    # Check for campaigns in new hierarchical structure
    for campaign_folder in campaigns_dir.iterdir():
        if campaign_folder.is_dir():
            campaign_file = campaign_folder / "campaign.json"
            if campaign_file.exists():
                try:
                    with open(campaign_file, 'r') as f:
                        campaign_data = json.load(f)
                        if "id" not in campaign_data:
                            campaign_data["id"] = campaign_folder.name
                        campaigns.append({
                            "id": campaign_data.get("id"),
                            "name": campaign_data.get("name"),
                            "shorthand": campaign_data.get("shorthand"),
                            "type": campaign_data.get("type"),
                            "status": campaign_data.get("status")
                        })
                except json.JSONDecodeError:
                    continue
    
    # Check for campaigns in old flat structure (for backward compatibility)
    for campaign_file in campaigns_dir.glob("*.json"):
        # Skip if we already found this campaign in new structure
        campaign_id = campaign_file.stem
        if any(c["id"] == campaign_id for c in campaigns):
            continue
            
        try:
            with open(campaign_file, 'r') as f:
                campaign_data = json.load(f)
                if "id" not in campaign_data:
                    campaign_data["id"] = campaign_id
                campaigns.append({
                    "id": campaign_data.get("id"),
                    "name": campaign_data.get("name"),
                    "shorthand": campaign_data.get("shorthand"),
                    "type": campaign_data.get("type"),
                    "status": campaign_data.get("status")
                })
        except json.JSONDecodeError:
            continue
    
    return campaigns

def load_reference_data(data_type):
    """Load reference data (bases, airframes, etc.) with caching for performance"""
    data_path = Path(current_app.instance_path) / "data" / f"{data_type}.json"
    
    if not data_path.exists():
        return {}
    
    # Use cached loading for reference data since it's rarely changed
    return get_cached_json(str(data_path))

def load_json(path, use_cache=False):
    """Load JSON data from a file path.
    
    Args:
        path: File path to load
        use_cache: If True, use caching for better performance (only for static files)
    """
    if use_cache:
        return get_cached_json(path)
    else:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

def save_json(path, data):
    """Save JSON data to a file path."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)