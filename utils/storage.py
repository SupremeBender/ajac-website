import os
import json
from pathlib import Path
import uuid
from datetime import datetime
from flask import current_app

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

def generate_mission_id(operation_code, mission_type, sequence_number=None):
    """Generate a mission ID following ATO conventions.
    Args:
        operation_code: Shorthand code for the operation (e.g., "PP15")
        mission_type: EX for exercise, OP for operation (from campaign)
        sequence_number: Sequence number within the operation (auto-incremented)
    Format: [OPERATION_CODE] | [EX/OP][SEQUENCE]
    Examples: PP15 | EX01, RF22 | OP03
    """
    if not operation_code:
        raise ValueError("Operation code is required (from campaign shorthand)")
    operation_code = operation_code.strip().upper()
    mission_type = mission_type.upper() if mission_type.upper() in ["EX", "OP"] else "EX"
    if not sequence_number:
        data_dir = ensure_data_dirs()
        # Use simple filename: e.g., PP15EX01.json
        pattern = f"{operation_code}{mission_type}*.json"
        existing_missions = list(data_dir.glob(pattern))
        highest_seq = 0
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
    """Save mission data to JSON file"""
    data_dir = ensure_data_dirs()
    mission_id = mission_data.get("id")
    
    if not mission_id:
        mission_id = generate_mission_id("", "EX")
        mission_data["id"] = mission_id
    
    file_path = data_dir / mission_id_to_filename(mission_id)
    
    with open(file_path, 'w') as f:
        json.dump(mission_data, f, indent=4)
    
    return mission_id

def save_campaign(campaign_data):
    """Save campaign data to JSON file"""
    data_dir = ensure_campaign_data_dir()
    campaign_id = campaign_data.get("id")
    if not campaign_id:
        # Use shorthand as ID
        campaign_id = campaign_data.get("shorthand", str(uuid.uuid4()))
        campaign_data["id"] = campaign_id
    file_path = data_dir / campaign_id_to_filename(campaign_id)
    with open(file_path, 'w') as f:
        json.dump(campaign_data, f, indent=4)
    return campaign_id

def load_mission(mission_id):
    """Load a mission by its simplified ID (e.g. PP15EX01). Always set mission['id'] and mission['name']."""
    data_dir = ensure_data_dirs()
    file_path = data_dir / mission_id_to_filename(mission_id)
    if not file_path.exists():
        return None
    with open(file_path, 'r', encoding='utf-8') as f:
        mission = json.load(f)
    # Always set 'id' to the filename (PP15EX01), and 'name' to the stylized name (PP15 | EX01)
    mission['id'] = mission_id
    mission['name'] = mission.get('id_raw') or mission.get('name') or mission.get('id')
    if 'id_raw' in mission:
        del mission['id_raw']
    return mission

def load_campaign(campaign_id):
    """Load campaign data from JSON file"""
    data_dir = ensure_campaign_data_dir()
    file_path = data_dir / campaign_id_to_filename(campaign_id)
    if not file_path.exists():
        return None
    with open(file_path, 'r') as f:
        return json.load(f)

def list_missions():
    """List all missions, returning a list of dicts with 'id' (PP15EX01) and 'name' (PP15 | EX01)"""
    missions_dir = os.path.join(os.path.dirname(__file__), '../instance/missions')
    missions = []
    for fname in os.listdir(missions_dir):
        if fname.endswith('.json'):
            mission_id = fname[:-5]
            with open(os.path.join(missions_dir, fname), 'r', encoding='utf-8') as f:
                mission = json.load(f)
            mission['id'] = mission_id
            mission['name'] = mission.get('id_raw') or mission.get('name') or mission.get('id')
            if 'id_raw' in mission:
                del mission['id_raw']
            missions.append(mission)
    missions.sort(key=lambda m: m.get('time_real', ''))
    return missions

def list_campaigns():
    """List all campaigns"""
    data_dir = ensure_campaign_data_dir()
    campaigns = []
    for campaign_file in data_dir.glob("*.json"):
        with open(campaign_file, 'r') as f:
            try:
                campaign_data = json.load(f)
                if "id" not in campaign_data:
                    campaign_data["id"] = campaign_file.stem
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
    """Load reference data (bases, airframes, etc.)"""
    data_path = Path(current_app.root_path) / "data" / f"{data_type}.json"
    
    if not data_path.exists():
        return {}
    
    with open(data_path, 'r') as f:
        return json.load(f)

def load_json(path):
    """Load JSON data from a file path."""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_json(path, data):
    """Save JSON data to a file path."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=4)