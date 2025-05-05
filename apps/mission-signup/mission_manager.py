import json
import os
from datetime import datetime, date
import tempfile
import shutil
import re

class MissionManager:
    def __init__(self):
        self.missions_dir = 'missions'
        if not os.path.exists(self.missions_dir):
            os.makedirs(self.missions_dir)
        
        # Load squadron data
        with open('config/squadrons.json') as f:
            self.squadron_data = json.load(f)

        # Load aircraft data
        with open('config/aircraft.json') as f:
            self.aircraft_data = json.load(f)

    def create_mission(self, name, mission_date, runways=None):
        """Create a new mission file"""
        mission_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        mission_data = {
            "id": mission_id,
            "name": name,
            "date": mission_date,
            "status": "OPEN",
            "bases": {},
            "flights": [],
            "assigned_tacans": [],
            "assigned_transponders": [],
            "assigned_frequencies": [],
            "change_requests": [],
            "runways": runways or {}  # Store runway selections
        }
        self._save_mission(mission_id, mission_data)
        return mission_id

    def get_all_missions(self):
        """Get list of all missions"""
        missions = []
        for filename in os.listdir(self.missions_dir):
            if filename.endswith('.json'):
                missions.append(self._load_mission(filename[:-5]))
        return missions

    def get_mission(self, mission_id):
        """Get a specific mission by ID"""
        return self._load_mission(mission_id)

    def add_flight(self, mission_id, flight_data):
        """Add a flight to a mission, handling all assignments and validation"""
        try:
            mission = self._load_mission(mission_id)
            
            # Handle joining an existing flight as a wingman
            if "callsign_prefix" in flight_data and "desired_slot" in flight_data:
                return self._join_flight_as_wingman(mission, flight_data)
            else:
                # Normal flight creation (lead)
                return self._create_new_flight(mission, flight_data)
            
        except Exception as e:
            return False, str(e)

    def _create_new_flight(self, mission, flight_data):
        """Create a new flight in the mission (flight lead)"""
        squadron_id = flight_data['squadron']
        
        # Get available callsigns for this squadron
        squadron_callsigns = self.squadron_data[squadron_id].get('callsigns', [])
        if not squadron_callsigns:
            # Fallback to the squadron name if no callsign bank defined
            squadron_callsigns = [self.squadron_data[squadron_id]['name']]
        
        # Initialize used_callsigns in mission if it doesn't exist
        if 'used_callsigns' not in mission:
            mission['used_callsigns'] = []
            
        # Find an available callsign for this flight
        available_callsigns = [cs for cs in squadron_callsigns if cs not in mission['used_callsigns']]
        
        if not available_callsigns:
            return False, f"No more callsigns available for squadron {squadron_id}"
            
        # Select the first available callsign
        selected_callsign = available_callsigns[0]
        
        # Find all used flight numbers across ALL flights to ensure global uniqueness
        used_flight_numbers = set()
        for flight in mission['flights']:
            match = re.search(r'\s(\d+)$', flight['callsign'])
            if match:
                flight_num = int(match.group(1))
                used_flight_numbers.add(flight_num)
        
        # Find next available flight number
        flight_num = 0
        while flight_num in used_flight_numbers:
            flight_num += 1
            
        if flight_num > 9:
            return False, "No more flight numbers available"
        
        # Mark this callsign as used
        mission['used_callsigns'].append(selected_callsign)
        
        # Assign TACAN
        tacan = self._assign_next_tacan(mission)
        if not tacan:
            return False, "No TACAN channels available"

        # Assign transponder block
        transponder_block = self._assign_next_transponder(mission)
        if not transponder_block:
            return False, "No transponder codes available"

        # Assign frequency
        freq = self._assign_frequency(mission)
        if not freq:
            return False, "No frequencies available"

        # Create new flight structure with unique callsign
        new_flight = {
            "squadron": squadron_id,
            "callsign": f"{selected_callsign} {flight_num}",
            "aircraft_type": flight_data['aircraft_type'],
            "area": flight_data['area'],
            "departure": flight_data['departure'],
            "recovery": flight_data['recovery'],
            "route": flight_data['route'],
            "tacan": tacan,
            "Reserved IFF": transponder_block,
            "frequency": freq,
            "members": {}
        }
        
        # Add intentions if provided
        if 'intentions' in flight_data and flight_data['intentions']:
            new_flight['intentions'] = flight_data['intentions']
        
        # Get aircraft base information
        aircraft_base = self.aircraft_data.get(flight_data['aircraft'], {}).get('base', '')
        
        # Add the flight lead as the first member
        pilot_name = flight_data.get('pilot_name', 'LEAD')
        new_flight['members'][pilot_name] = {
            "aircraft": flight_data['aircraft'],
            "IFF": transponder_block[0],
            "callsign": f"{selected_callsign}{flight_num}1",
            "base": aircraft_base,
            "is_cross_base": False  # Lead always sets the base, so never cross-base
        }
        
        mission['flights'].append(new_flight)
        self._save_mission(mission['id'], mission)
        
        # Return the updated flight info
        return True, new_flight

    def _join_flight_as_wingman(self, mission, flight_data):
        """Join an existing flight as a wingman"""
        callsign_prefix = flight_data['callsign_prefix']
        desired_slot = int(flight_data['desired_slot'])
        
        # Find the target flight
        target_flight = None
        for flight in mission['flights']:
            if flight['callsign'].strip() == callsign_prefix.strip():  # Handle potential whitespace issues
                target_flight = flight
                break
                
        if not target_flight:
            return False, f"Flight {callsign_prefix} not found"
        
        # Check if slot is already taken
        for member in target_flight['members'].values():
            if str(desired_slot) in member['callsign'][-1:]:  # More robust slot check
                return False, f"Slot {desired_slot} is already taken in {callsign_prefix}"
        
        # Validate aircraft compatibility
        lead_aircraft_type = target_flight['aircraft_type']
        wing_aircraft = self.aircraft_data.get(flight_data['aircraft'])
        if not wing_aircraft:
            return False, f"Aircraft {flight_data['aircraft']} not found in configuration"
            
        if wing_aircraft.get('type') != lead_aircraft_type:
            return False, f"Aircraft type {wing_aircraft.get('type')} is not compatible with flight lead's {lead_aircraft_type}"
            
        # Get squadron and flight number from callsign prefix
        match = re.match(r'([A-Za-z]+)\s*(\d+)', callsign_prefix.strip())
        if not match:
            return False, f"Invalid callsign format: {callsign_prefix}"
            
        squadron_callsign = match.group(1)
        flight_num = match.group(2)
        
        # Create callsign for the new member
        new_callsign = f"{squadron_callsign}{flight_num}{desired_slot}"
        
        # Validate IFF code availability
        if desired_slot < 1 or desired_slot > len(target_flight['Reserved IFF']):
            return False, f"Invalid slot number {desired_slot}. Must be between 1 and {len(target_flight['Reserved IFF'])}"
            
        # Check if this is a cross-base aircraft
        aircraft_base = wing_aircraft.get('base', '')
        lead_base = target_flight['departure']['base']
        is_cross_base = aircraft_base != lead_base
            
        # Add new member to the flight
        pilot_name = flight_data.get('pilot_name', '').strip() or f'PILOT{desired_slot}'
        target_flight['members'][pilot_name] = {
            "aircraft": flight_data['aircraft'],
            "IFF": target_flight['Reserved IFF'][desired_slot-1],
            "callsign": new_callsign,
            "base": aircraft_base,
            "is_cross_base": is_cross_base
        }
        
        # Save the updated mission
        self._save_mission(mission['id'], mission)
        
        # Return success and the updated flight
        return True, target_flight

    def lock_mission(self, mission_id):
        """Lock a mission to prevent further changes"""
        mission = self._load_mission(mission_id)
        mission["status"] = "LOCKED"
        self._save_mission(mission_id, mission)
        return self._generate_lotatc_correlation(mission)

    def _assign_next_tacan(self, mission):
        """Assign next available TACAN channel"""
        used = set(mission["assigned_tacans"])
        for i in range(1, 64):
            if i not in used:
                mission["assigned_tacans"].append(i)
                return f"{i}Y/{i+63}Y"
        return None

    def _assign_next_transponder(self, mission):
        """Assign next available transponder block. Only uses octal digits (0-7)"""
        used = set(mission["assigned_transponders"])
        
        # Start from 1000 and increment by 10, but ensure all digits are 0-7
        for i in range(1000, 7777, 10):
            # Convert to string to check digits
            code = str(i)
            # Skip if any digit is 8 or 9
            if any(d > '7' for d in code):
                continue
            
            if i not in used:
                mission["assigned_transponders"].append(i)
                # Create a block of 4 transponder codes
                return [i, i+1, i+2, i+3]
        return None

    def _assign_frequency(self, mission):
        """Assign next available frequency"""
        with open('config/frequencies.json') as f:
            freq_data = json.load(f)
        
        used = set(mission["assigned_frequencies"])
        frequency_list = freq_data["intraflight"]["frequencies"]
        common_freqs = freq_data["common"]
        
        for freq in frequency_list:
            # Check if frequency is not already used and not in common frequencies
            if freq not in used and freq not in common_freqs:
                mission["assigned_frequencies"].append(freq)
                return f"{freq:.3f}"
        return None

    def _generate_lotatc_correlation(self, mission):
        """Generate LotATC correlation file"""
        correlation = {
            "__comments": f"Transponder codes for {mission['name']}",
            "enable": True,
            "transponders": []
        }
        
        # Process each flight
        for flight in mission["flights"]:
            # Process each member in the flight
            for member_name, member_data in flight["members"].items():
                correlation["transponders"].append({
                    "mode3": str(member_data["IFF"]),
                    "name": member_name,
                    "type": flight["aircraft_type"],
                    "callsign": member_data["callsign"]
                })
        
        return correlation

    def _save_mission(self, mission_id, data):
        """Save mission data to file using a temporary file for safety"""
        filepath = os.path.join(self.missions_dir, f"{mission_id}.json")
        
        # Write to temporary file first
        temp_fd, temp_path = tempfile.mkstemp(text=True)
        try:
            with os.fdopen(temp_fd, 'w') as f:
                json.dump(data, f, indent=4)
            
            # If write was successful, move temp file to final location
            shutil.move(temp_path, filepath)
        except Exception as e:
            # Clean up temp file in case of error
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise e

    def _load_mission(self, mission_id):
        """Load mission data from file"""
        filepath = os.path.join(self.missions_dir, f"{mission_id}.json")
        with open(filepath) as f:
            return json.load(f)
            
    def migrate_old_mission_format(self, mission_id):
        """Migrate an old-format mission to the new format"""
        mission = self._load_mission(mission_id)
        
        # Check if already in new format
        if mission['flights'] and 'members' in mission['flights'][0]:
            return True, "Mission already in new format"
            
        new_flights = []
        
        # Group flights by callsign prefix (e.g., LION0, LION1, etc.)
        flight_groups = {}
        for flight in mission['flights']:
            # Extract prefix (remove last digit)
            callsign = flight['callsign']
            prefix = callsign[:-1]
            flight_num = prefix[-1] if prefix and prefix[-1].isdigit() else '0'
            squadron_callsign = prefix[:-1] if prefix and prefix[-1].isdigit() else prefix
            
            # Create group key
            group_key = f"{squadron_callsign} {flight_num}"
            
            if group_key not in flight_groups:
                flight_groups[group_key] = []
                
            flight_groups[group_key].append(flight)
            
        # Create new flight structure for each group
        for group_key, flights in flight_groups.items():
            # Sort flights by callsign (to ensure lead is first)
            flights.sort(key=lambda f: f['callsign'])
            
            # Get lead flight
            lead_flight = flights[0]
            
            # Create new flight structure
            new_flight = {
                "squadron": lead_flight['squadron'],
                "callsign": group_key,
                "aircraft_type": lead_flight['aircraft_type'],
                "area": lead_flight['area'],
                "departure": lead_flight['departure'],
                "recovery": lead_flight['recovery'],
                "route": lead_flight['route'],
                "tacan": lead_flight['tacan'],
                "Reserved IFF": self._get_iff_block_for_flight(lead_flight['transponder']),
                "frequency": lead_flight['frequency'],
                "members": {}
            }
            
            # Add all members
            for flight in flights:
                # Extract pilot slot from callsign (last digit)
                slot = flight['callsign'][-1]
                pilot_name = f"PILOT{slot}"
                
                new_flight['members'][pilot_name] = {
                    "aircraft": flight['aircraft'],
                    "IFF": flight['transponder'],
                    "callsign": flight['callsign']
                }
                
            new_flights.append(new_flight)
            
        # Update mission with new flights
        mission['flights'] = new_flights
        
        # Save updated mission
        self._save_mission(mission_id, mission)
        
        return True, "Mission migrated to new format"
        
    def _get_iff_block_for_flight(self, transponder):
        """Generate a block of 4 IFF codes based on a lead transponder"""
        base = transponder - (transponder % 10)
        return [base, base+1, base+2, base+3]
        
    def migrate_all_missions(self):
        """Migrate all missions to the new format"""
        results = []
        for filename in os.listdir(self.missions_dir):
            if filename.endswith('.json'):
                mission_id = filename[:-5]
                success, message = self.migrate_old_mission_format(mission_id)
                results.append({
                    "mission_id": mission_id,
                    "success": success,
                    "message": message
                })
        return results
