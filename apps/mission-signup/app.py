from flask import Flask, render_template, request, jsonify, redirect, url_for, session
import json, re
import os
import platform
import time
from datetime import datetime
from mission_manager import MissionManager
import secrets
from werkzeug.middleware.proxy_fix import ProxyFix

app = Flask(__name__)

# Environment-based configuration
ENVIRONMENT = os.getenv('FLASK_ENV', 'production')  # Default to production
URL_PREFIX = os.getenv('URL_PREFIX', '')  # Empty for local, '/blue' for Apache

# Remove the hard-coded proxy fix and make it configurable
if os.getenv('BEHIND_PROXY', 'false').lower() == 'true':
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Make the URL prefix configurable
app.config['APPLICATION_ROOT'] = URL_PREFIX

# Configure app based on environment
app.config.update(
    # Core settings
    APPLICATION_ROOT=URL_PREFIX,
    SESSION_COOKIE_NAME='mission_signup_session',
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    PERMANENT_SESSION_LIFETIME=86400,
    
    # Environment-specific settings
    SESSION_COOKIE_SECURE=ENVIRONMENT == 'production',
    SESSION_COOKIE_PATH=URL_PREFIX or '/',
    SERVER_NAME=os.getenv('SERVER_NAME')
)

# Only apply proxy fix in production/Apache
if ENVIRONMENT == 'production':
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Read password from file
PASSWORD_FILE = os.path.join(os.path.dirname(__file__), 'auth', 'blufor_passwd')
try:
    with open(PASSWORD_FILE, 'r') as f:
        SITE_PASSWORD = f.read().strip()
        print(f"[INIT] Loaded password from {PASSWORD_FILE}: '{SITE_PASSWORD}'")
except FileNotFoundError:
    print(f"[WARNING] Password file not found: {PASSWORD_FILE}, using default")
    SITE_PASSWORD = "password"

# Derive secret key from password - this way when password changes, all sessions are invalidated
app.secret_key = f"mission-signup-{SITE_PASSWORD}"


def load_config(filename):
    try:
        config_path = os.path.join(os.path.dirname(__file__), 'config', filename)
        with open(config_path) as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Configuration file '{filename}' not found at {config_path}")
        return {}
    except json.JSONDecodeError as e:
        print(f"[ERROR] Failed to parse JSON in '{filename}': {e}")
        return {}

# Load configuration files
print("[INIT] Loading configuration files")
aircraft_data = load_config('aircraft.json')
squadron_data = load_config('squadrons.json')
base_data = load_config('bases.json')
procedures_data = load_config('procedures.json')
airspace_data = load_config('airspace.json')
frequency_data = load_config('frequencies.json')

def get_squadron_callsign(squadron):
    print(f"[DEBUG] Fetching callsign for squadron: {squadron}")
    return squadron_data.get(squadron, {}).get('name', 'UNKNOWN')

def get_squadron_bases(squadron):
    """Get all bases where a squadron currently has aircraft parked"""
    if not squadron:
        return []
    print(f"[DEBUG] Getting bases for squadron {squadron}")
    
    # Only look at where aircraft are currently parked, according to aircraft.json
    bases = set()
    aircraft_found = 0
    for tail, meta in aircraft_data.items():
        if meta.get('squadron') == squadron:
            aircraft_found += 1
            current_base = meta.get('base')
            if current_base:
                print(f"[DEBUG] Found aircraft {tail} for squadron {squadron} at base {current_base}")
                bases.add(current_base)
    
    result = sorted(list(bases))
    print(f"[DEBUG] Found {aircraft_found} aircraft for squadron {squadron}")
    print(f"[DEBUG] Final bases for {squadron}: {result}")
    return result

def get_vfr_departures(base):
    print(f"[DEBUG] Fetching VFR departures for base: {base}")
    return procedures_data.get('vfr_departures', {}).get(base, {}).keys()

def get_ifr_departures(base, runway):
    print(f"[DEBUG] Fetching IFR departures for base: {base}, runway: {runway}")
    if not base or not runway:
        return []
    departures = procedures_data.get('ifr_departures', {}).get(base, {}).get(runway, [])
    print(f"[DEBUG] Found departures: {departures}")
    return departures

def get_ifr_recoveries(base, runway):
    print(f"[DEBUG] Fetching IFR recoveries for base: {base}, runway: {runway}")
    if not base or not runway:
        return []
    recoveries = procedures_data.get('ifr_recoveries', {}).get(base, {}).get(runway, [])
    print(f"[DEBUG] Found recoveries: {recoveries}")
    return recoveries

def get_route_variants(dep_base, rec_base, area, direction):
    """Get available route variants for the given parameters"""
    area_key = area.replace(" ", "_")
    area_data = airspace_data.get('areas', {}).get(area_key, {})
    
    if not area_data:
        return []

    # Only show variants for the correct base and direction
    if direction == 'inbound':
        base = dep_base
    else:
        base = rec_base

    base_transitions = area_data.get('transitions', {}).get(base, {})
    direction_data = base_transitions.get(direction, {})
    
    variants = []
    if direction_data:
        variants.append("Primary")  # Always add primary route
        # Only add variants for ENDU when it's the departure base and going to POLAR_WEST
        if 'variants' in direction_data and not (
            area_key == "POLAR_WEST" and 
            dep_base == "ENDU" and 
            'conditions' in direction_data):
            variants.extend(list(direction_data['variants'].keys()))
    
    return variants

def get_route(dep_base, dep_proc, area, rec_proc, rec_base, squadron):
    """
    Generate route based on holding points with proper segment handling.
    Format: [DEP_BASE] [DEP_PROCEDURE] [TRANSITION] [HOLDING_POINT] [TRANSITION] [REC_PROCEDURE] [REC_BASE]
    """
    print(f"[DEBUG] Generating route: {dep_base} {dep_proc} -> {area} -> {rec_proc} {rec_base}")
    
    # Find the holding point for this area
    holding_point = None
    for point, data in airspace_data.get('holding_points', {}).items():
        if data['area'].upper() == area:
            holding_point = point
            print(f"[DEBUG] Found holding point {holding_point} for area {area}")
            break
    
    if not holding_point:
        print(f"[ERROR] No holding point found for area {area}")
        return ""

    route_parts = []
    
    # 1. Add departure base and procedure
    route_parts.extend([dep_base, dep_proc])
    
    # 2. Get inbound transition (base to holding point)
    transitions = airspace_data['holding_points'][holding_point]['transitions'].get(dep_base, {})
    if transitions and 'inbound' in transitions and transitions['inbound']:
        print(f"[DEBUG] Adding inbound transitions: {transitions['inbound']}")
        route_parts.extend(transitions['inbound'])
    else:
        print(f"[DEBUG] No inbound transitions found for {dep_base} to {holding_point}")
    
    # 3. Add holding point
    route_parts.append(holding_point)
    
    # 4. Get outbound transition (holding point to recovery base)
    transitions = airspace_data['holding_points'][holding_point]['transitions'].get(rec_base, {})
    if transitions and 'outbound' in transitions and transitions['outbound']:
        print(f"[DEBUG] Adding outbound transitions: {transitions['outbound']}")
        route_parts.extend(transitions['outbound'])
    else:
        print(f"[DEBUG] No outbound transitions found for {holding_point} to {rec_base}")
    
    # 5. Add recovery procedure and base
    route_parts.extend([rec_proc, rec_base])
    
    full_route = " ".join(route_parts).upper()
    print(f"[DEBUG] Generated route: {full_route}")

    # Get squadron's callsign directly from squadron_data
    callsign = squadron_data.get(squadron, {}).get('name', 'UNKNOWN')
    formatted_output = f"{callsign}\n{full_route}"
    return formatted_output

def get_available_flights(mission, squadron=None):
    """Get list of flights that can accept wingmen (less than 4 aircraft)"""
    available = []
    if not mission or mission["status"] == "LOCKED":
        return available
        
    # With new structure, we just need to check flights that have fewer than 4 members
    for flight in mission["flights"]:
        if len(flight.get("members", {})) < 4:
            # If squadron specified, only show flights from that squadron
            if not squadron or flight["squadron"] == squadron:
                available.append(flight)
    
    return available

def get_available_aircraft(mission, squadron, base, lead_flight=None):
    """Get list of available aircraft for a squadron/base that aren't already in use
    If lead_flight is provided, only return compatible aircraft, regardless of base"""
    # Get all aircraft already in use in this mission
    used_aircraft = set()
    for flight in mission.get('flights', []):
        for member in flight.get('members', {}).values():
            used_aircraft.add(member['aircraft'])
    
    # If joining a flight, we need to match the lead's aircraft type
    if lead_flight:
        required_type = lead_flight['aircraft_type']
        lead_base = lead_flight['departure']['base']
        
        # Get all compatible aircraft for the squadron, regardless of base
        available = []
        for tail, meta in aircraft_data.items():
            if (meta.get('squadron') == squadron and 
                meta.get('type') == required_type and 
                tail not in used_aircraft):
                # Add aircraft info with base information for display
                aircraft_base = meta.get('base', '')
                is_cross_base = (aircraft_base != lead_base)
                available.append({
                    'tail': tail,
                    'base': aircraft_base,
                    'is_cross_base': is_cross_base
                })
        
        # Sort by base status (same base first), then by tail number
        return sorted(available, key=lambda x: (x['is_cross_base'], x['tail']))
    else:
        # Normal flight lead - get all aircraft for the squadron/base
        available = [
            tail for tail, meta in aircraft_data.items()
            if meta.get('squadron') == squadron 
            and meta.get('base') == base 
            and tail not in used_aircraft
        ]
    
        return sorted(available)

def get_procedures(base, proc_type, base_config, dep_type):
    """Get procedures for a base with proper grouping and styling"""
    if dep_type == "VFR":
        procs = list(procedures_data.get('vfr_departures', {}).get(base, {}).keys())
        return [('VFR', sorted(procs))]
    
    # For IFR, check active runway
    result = []
    runway_in_use = base_config.get('runway_in_use')
    active_procs = []
    other_procs = []
    
    # Get procedures by runway
    if proc_type == 'dep':
        procs_by_rwy = procedures_data.get('ifr_departures', {}).get(base, {})
    else:
        procs_by_rwy = procedures_data.get('ifr_recoveries', {}).get(base, {})
    
    # First get procedures for active runway
    if runway_in_use:
        rwy_key = f"RUNWAY {runway_in_use}"
        active_procs = procs_by_rwy.get(rwy_key, [])
    
    # Then get other procedures
    for rwy, procs in procs_by_rwy.items():
        if not runway_in_use or not rwy == f"RUNWAY {runway_in_use}":
            other_procs.extend(procs)
    
    # Build the groups
    if active_procs:
        result.append(('Active Runway', sorted(active_procs)))
    if other_procs:
        result.append(('Other Runways', sorted(other_procs)))
        
    return result

mission_manager = MissionManager()

@app.route(f'{URL_PREFIX}/missions')
@app.route('/missions')
def get_missions():
    try:
        # Get team from URL prefix
        team = 'blue' if URL_PREFIX == '/blue' else 'red' if URL_PREFIX == '/red' else None
        missions = mission_manager.get_all_missions(team=team)
        return jsonify(missions)
    except Exception as e:
        print(f"[ERROR] Failed to get missions: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route(f'{URL_PREFIX}/create_mission', methods=['POST'])
@app.route('/create_mission', methods=['POST'])
def create_mission():
    try:
        name = request.form.get('mission_name')
        date = request.form.get('mission_date')
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', date):
            return {'status': 'error', 'message': 'Invalid date format'}
            
        # Collect runway selections
        runways = {}
        for base in base_data:
            rwy = request.form.get(f'rwy_{base}')
            if rwy:
                runways[base] = rwy
        
        mission_id = mission_manager.create_mission(name, date, runways)
        return {'status': 'success', 'mission_id': mission_id}
    except Exception as e:
        return {'status': 'error', 'message': str(e)}

@app.route('/new-flight-form', methods=['POST'])
def get_new_flight_form():
    """Direct endpoint to generate new flight form with appropriate options"""
    try:
        mission_id = request.form.get('mission_id', '')
        squadron = request.form.get('squadron', '')
        
        print(f"[DEBUG] /new-flight-form: mission_id={mission_id}, squadron={squadron}")
        
        # Prepare response data structure
        response_data = {
            'options': {},
            'errors': [],
            'selected': {}
        }
        
        # Get all squadrons for initial form
        squadrons = sorted(squadron_data.keys())
        squadron_options = ['<option value="">Choose your squadron</option>']
        for sqn in squadrons:
            squadron_options.append(f'<option value="{sqn}"{" selected" if sqn == squadron else ""}>{sqn}</option>')
        response_data['options']['squadron'] = ''.join(squadron_options)
        
        # If squadron is selected, populate bases for that squadron
        if squadron:
            # Get available bases - direct approach, no helper function
            # Look at aircraft data directly
            available_bases = set()
            print(f"[DEBUG] Looking for all aircraft for squadron {squadron}")
            
            # First try with squadron data (direct access)
            for tail, meta in aircraft_data.items():
                if meta.get('squadron') == squadron:
                    print(f"[DEBUG] Found aircraft {tail} for squadron {squadron} at {meta.get('base')}")
                    if 'base' in meta and meta['base']:
                        available_bases.add(meta['base'])
            
            # Ensure we have the response with hardcoded base data for common squadrons
            # This is a direct emergency fallback in the API endpoint itself
            if not available_bases:
                print(f"[DEBUG] No aircraft bases found, using emergency mapping")
                emergency_mapping = {
                    '331': ['ENBO', 'ENAN', 'ENDU'],
                    '440': ['CVN73'],
                    'NFSA': ['ENAN'],
                    '337': ['ENDU'],
                    '42': ['ESNQ']
                }
                if squadron in emergency_mapping:
                    available_bases = set(emergency_mapping[squadron])
            
            available_bases = sorted(list(available_bases))
            
            print(f"[DEBUG] Final available bases for squadron {squadron}: {available_bases}")
            
            # Departure bases
            dep_base_options = ['<option value="">Select departure base</option>']
            for base in available_bases:
                dep_base_options.append(f'<option value="{base}">{base}</option>')
            response_data['options']['dep_base'] = ''.join(dep_base_options)
            
            # Recovery bases (all bases)
            all_bases = sorted(base_data.keys())
            rec_base_options = ['<option value="">Select recovery base</option>']
            for base in all_bases:
                rec_base_options.append(f'<option value="{base}">{base}</option>')
            response_data['options']['rec_base'] = ''.join(rec_base_options)
            
            # Get training areas
            areas = set()
            for point_data in airspace_data.get('holding_points', {}).values():
                area_name = point_data.get('area', '')
                if area_name:
                    areas.add(area_name)
            area_list = sorted(filter(None, areas))
            
            area_options = ['<option value="">Select training area</option>']
            for area_name in area_list:
                area_options.append(f'<option value="{area_name}">{area_name}</option>')
            response_data['options']['training_area'] = ''.join(area_options)
        
        print(f"[DEBUG] /new-flight-form response: {response_data}")
        return jsonify(response_data)
    except Exception as e:
        print(f"[ERROR] New flight form: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)})

@app.route('/squadron-bases', methods=['POST'])
def get_squadron_bases_direct():
    """Direct endpoint to get base options for a squadron"""
    squadron = request.form.get('squadron', '')
    
    # Get bases directly from aircraft data
    bases = set()
    for tail, meta in aircraft_data.items():
        if meta.get('squadron') == squadron:
            if 'base' in meta and meta['base']:
                bases.add(meta['base'])
    
    # Sort the list of bases
    bases_list = sorted(list(bases))
    
    # Generate HTML for the dropdown options
    options_html = '<option value="">Select departure base</option>'
    for base in bases_list:
        options_html += f'<option value="{base}">{base}</option>'
    
    return jsonify({
        'html': options_html,
        'bases': bases_list
    })

@app.route('/squadron-aircraft', methods=['POST'])
def get_squadron_aircraft_direct():
    """Direct endpoint to get aircraft options for a squadron and base"""
    squadron = request.form.get('squadron', '')
    base = request.form.get('base', '')
    mission_id = request.form.get('mission_id', '')
    aircraft_type = request.form.get('aircraft_type', '')
    lead_callsign = request.form.get('callsign_prefix', '')
    
    # Print debug information
    print(f"[DEBUG] /squadron-aircraft: mission_id={mission_id}, squadron={squadron}, base={base}, aircraft_type={aircraft_type}, lead_callsign={lead_callsign}")
    
    selected_aircraft = []
    used_aircraft = set()
    lead_flight = None
    
    # If we have a mission, we need to exclude aircraft already assigned
    if mission_id and mission_id != '0' and mission_id.strip():
        try:
            mission = mission_manager.get_mission(mission_id)
            
            # Get all aircraft already in use in this mission
            for flight in mission.get('flights', []):
                for member in flight.get('members', {}).values():
                    used_aircraft.add(member['aircraft'])
                
                # Find the lead flight if we have a callsign
                if lead_callsign and flight.get('callsign') == lead_callsign:
                    lead_flight = flight
                    
        except (FileNotFoundError, KeyError) as e:
            # Handle missing mission file gracefully
            print(f"[WARNING] Mission file not found or invalid: {mission_id}. Error: {str(e)}")
            used_aircraft = set()  # Reset to empty set if mission not found
    else:
        print(f"[DEBUG] No valid mission_id provided or mission_id=0, skipping mission check")
    
    # Get aircraft options
    if lead_flight:
        # We're joining a flight, get all compatible aircraft for the squadron
        selected_aircraft = get_available_aircraft(
            mission if 'mission' in locals() else {'flights': []}, 
            squadron, 
            base,
            lead_flight
        )
        
        # Generate HTML for dropdown options with cross-base warning
        if selected_aircraft:
            options_html = '<option value="">Select your aircraft</option>'
            for aircraft in selected_aircraft:
                tail = aircraft['tail']
                base_info = ""
                if aircraft['is_cross_base']:
                    base_info = f" (at {aircraft['base']} - not the same as lead!)"
                options_html += f'<option value="{tail}">{tail}{base_info}</option>'
        else:
            options_html = '<option value="">No aircraft available</option>'
    else:
        # Normal flight lead selection - just filter by squadron and base
        filtered_aircraft = [
            tail for tail, meta in aircraft_data.items()
            if meta.get('squadron') == squadron and 
               meta.get('base') == base and
               tail not in used_aircraft
        ]
        selected_aircraft = sorted(filtered_aircraft)
        
        # Generate HTML for dropdown options (no cross-base warning needed)
        if selected_aircraft:
            options_html = '<option value="">Select your aircraft</option>'
            for tail in selected_aircraft:
                options_html += f'<option value="{tail}">{tail}</option>'
        else:
            options_html = '<option value="">No aircraft available</option>'
    
    return jsonify({
        'html': options_html,
        'aircraft': selected_aircraft
    })

@app.route('/get-procedures', methods=['POST'])
def get_procedures_endpoint():
    """Direct endpoint to get procedures for a base and type"""
    try:
        base = request.form.get('base', '')
        proc_type = request.form.get('proc_type', '')  # 'dep' or 'rec'
        dep_type = request.form.get('type', '')  # 'VFR' or 'IFR'
        mission_id = request.form.get('mission_id', '')
        
        print(f"[DEBUG] /get-procedures: base={base}, proc_type={proc_type}, dep_type={dep_type}, mission_id={mission_id}")
        
        if not base or not proc_type or not dep_type:
            return jsonify({'error': 'Missing required parameters'})
        
        # Get active runway from mission if available
        active_runway = None
        if mission_id:
            try:
                mission = mission_manager.get_mission(mission_id)
                if mission and 'runways' in mission:
                    active_runway = mission['runways'].get(base)
            except Exception as e:
                print(f"[WARNING] Error getting active runway: {e}")
        
        # Fallback to base_data if not in mission
        if not active_runway and base in base_data:
            active_runway = base_data[base].get('runway_in_use')
        
        print(f"[DEBUG] Active runway for {base}: {active_runway}")
        
        # Get procedures based on type
        options_html = '<option value="">Select Procedure</option>'
        procedures = []
        
        if dep_type == 'VFR':
            # Handle VFR procedures
            vfr_procs = procedures_data.get('vfr_departures' if proc_type == 'dep' else 'vfr_recoveries', {}).get(base, {})
            if vfr_procs:
                procedures = sorted(vfr_procs.keys())
                options_html += ''.join([f'<option value="{proc}">{proc}</option>' for proc in procedures])
        else:
            # Handle IFR procedures
            ifr_data = procedures_data.get('ifr_departures' if proc_type == 'dep' else 'ifr_recoveries', {}).get(base, {})
            
            if ifr_data:
                # Group by runway - active runway first
                if active_runway:
                    active_key = f"RUNWAY {active_runway}"
                    if active_key in ifr_data:
                        options_html += f'<optgroup label="Active Runway ({active_runway})">'
                        for proc in sorted(ifr_data[active_key]):
                            options_html += f'<option value="{proc}">{proc}</option>'
                            procedures.append(proc)
                        options_html += '</optgroup>'
                
                # Add other runways
                other_procs = []
                for rwy_key, procs in ifr_data.items():
                    if not active_runway or rwy_key != f"RUNWAY {active_runway}":
                        options_html += f'<optgroup label="{rwy_key}">'
                        for proc in sorted(procs):
                            options_html += f'<option value="{proc}">{proc}</option>'
                            other_procs.append(proc)
                        options_html += '</optgroup>'
                
                procedures.extend(other_procs)
        
        return jsonify({
            'html': options_html,
            'procedures': procedures
        })
    except Exception as e:
        print(f"[ERROR] Get procedures endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)})

@app.route('/squadron-bases', methods=['POST'])
def squadron_bases_endpoint():
    """Endpoint to get bases for a squadron"""
    try:
        squadron = request.form.get('squadron', '')
        if not squadron:
            return jsonify({'error': 'Squadron parameter is required'})
            
        # Get bases directly from aircraft data
        bases = set()
        for tail, meta in aircraft_data.items():
            if meta.get('squadron') == squadron:
                if 'base' in meta and meta['base']:
                    bases.add(meta['base'])
        
        # Sort the list of bases
        bases_list = sorted(list(bases))
        
        # Generate HTML for the dropdown options
        options_html = '<option value="">Select departure base</option>'
        for base in bases_list:
            options_html += f'<option value="{base}">{base}</option>'
        
        return jsonify({
            'html': options_html,
            'bases': bases_list
        })
    except Exception as e:
        print(f"[ERROR] Squadron bases endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)})

@app.route('/squadron-aircraft', methods=['POST'])
def squadron_aircraft_endpoint():
    """Endpoint to get aircraft for a squadron and base"""
    try:
        squadron = request.form.get('squadron', '')
        base = request.form.get('base', '')
        mission_id = request.form.get('mission_id', '')
        aircraft_type = request.form.get('aircraft_type', '')
        
        if not squadron or not base:
            return jsonify({'error': 'Squadron and base parameters are required'})
        
        # Print debug information
        print(f"[DEBUG] /squadron-aircraft: squadron={squadron}, base={base}, aircraft_type={aircraft_type}, mission_id={mission_id}")
        
        selected_aircraft = []
        used_aircraft = set()
        
        # If we have a mission, we need to exclude aircraft already assigned
        if mission_id:
            try:
                mission = mission_manager.get_mission(mission_id)
                
                # Get all aircraft already in use in this mission
                for flight in mission.get('flights', []):
                    for member in flight.get('members', {}).values():
                        used_aircraft.add(member['aircraft'])
            except Exception as e:
                # Handle missing mission file gracefully
                print(f"[WARNING] Error getting mission: {str(e)}")
                used_aircraft = set()
        
        # Filter by aircraft type if provided (for joining a flight)
        if aircraft_type:
            # Get compatible aircraft for the squadron/base that match the required type
            selected_aircraft = [
                tail for tail, meta in aircraft_data.items()
                if meta.get('squadron') == squadron and 
                   meta.get('base') == base and 
                   meta.get('type') == aircraft_type and
                   tail not in used_aircraft
            ]
        else:
            # No specific aircraft type - just get all aircraft for the squadron/base
            selected_aircraft = [
                tail for tail, meta in aircraft_data.items()
                if meta.get('squadron') == squadron and 
                   meta.get('base') == base and
                   tail not in used_aircraft
            ]
        
        selected_aircraft = sorted(selected_aircraft)
        
        # Generate HTML for dropdown options
        if selected_aircraft:
            options_html = '<option value="">Select your aircraft</option>'
            for tail in selected_aircraft:
                options_html += f'<option value="{tail}">{tail}</option>'
        else:
            options_html = '<option value="">No aircraft available</option>'
        
        return jsonify({
            'html': options_html,
            'aircraft': selected_aircraft
        })
    except Exception as e:
        print(f"[ERROR] Squadron aircraft endpoint: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)})

@app.route('/get-procedures', methods=['POST'])
def get_procedures_blue_endpoint():
    """Endpoint to get procedures for a base and type"""
    # Redirect to the main procedures endpoint
    return get_procedures_endpoint()

@app.route('/migrate-missions', methods=['POST'])
def migrate_missions():
    """Endpoint to migrate missions to the new format"""
    try:
        if request.form.get('mission_id'):
            # Migrate a specific mission
            mission_id = request.form.get('mission_id')
            success, message = mission_manager.migrate_old_mission_format(mission_id)
            return jsonify({
                'status': 'success' if success else 'error',
                'message': message,
                'mission_id': mission_id
            })
        else:
            # Migrate all missions
            results = mission_manager.migrate_all_missions()
            return jsonify({
                'status': 'success',
                'results': results
            })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        })

@app.route(f'{URL_PREFIX}/login', methods=['GET', 'POST'])
@app.route('/login', methods=['GET', 'POST'])
@app.route('/blue/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        if request.form['password'] == SITE_PASSWORD:
            session.permanent = True  # Make session permanent
            session['logged_in'] = True
            return redirect(url_for('flight_plan', _external=True))
        else:
            error = 'Invalid password. Please try again.'
    
    return render_template('login.html', error=error)

@app.route(f'{URL_PREFIX}/', methods=['GET', 'POST'])
@app.route('/', methods=['GET', 'POST'])
def flight_plan():
    # Check if user is logged in
    if not session.get('logged_in'):
        return redirect(url_for('login', _external=True))
        
    print("[ROUTE] Received request")
    print(f"[DEBUG] Form data: {dict(request.form)}")
    output = ""
    route_preview = False
    is_ajax = request.form.get('partial_update') == 'true'
    
    # Always initialize these before any use
    selected_aircraft = []
    available_bases = []
    all_bases = sorted(base_data.keys())
    dep_procs = []
    rec_procs = []
    
    # Get areas list from holding points right away
    areas = set()
    for point_data in airspace_data.get('holding_points', {}).values():
        area_name = point_data.get('area', '')
        if area_name:
            areas.add(area_name)
    area_list = sorted(filter(None, areas))
    
    try:
        # Initialize all form variables
        mission_id = request.form.get('mission_id', '')
        selected_flight = request.form.get('join_flight', '')
        squadron = request.form.get('squadron', '')
        dep_base = request.form.get('dep_base', '')
        aircraft_tail = request.form.get('aircraft', '')
        dep_type = request.form.get('dep_type', '')
        dep_proc = request.form.get('dep_proc', '').upper()
        area = request.form.get('training_area', '').upper()
        rec_base = request.form.get('rec_base', '')
        rec_type = request.form.get('rec_type', '')
        rec_proc = request.form.get('rec_proc', '').upper()
        callsign_prefix = request.form.get('callsign_prefix', '').strip()
        desired_slot = request.form.get('desired_slot', '')
        pilot_name = request.form.get('pilot_name', '').strip()

        # Get current mission right away if selected
        current_mission = None
        available_flights = []
        lead_flight = None
        if mission_id:
            try:
                current_mission = mission_manager.get_mission(mission_id)
                if current_mission:
                    available_flights = get_available_flights(current_mission)
                    # If joining a flight, get squadron and base from lead
                    if callsign_prefix and desired_slot:
                        for flight in current_mission['flights']:
                            if flight['callsign'] == callsign_prefix:
                                squadron = flight['squadron']
                                dep_base = flight['departure']['base']
                                lead_flight = flight
                                break
            except Exception as e:
                print(f"[ERROR] Failed to load mission: {e}")
                current_mission = None
                available_flights = []

        # Validate pilot name format
        if pilot_name and not re.match(r'^[A-Za-z0-9_-]+$', pilot_name):
            raise ValueError("Pilot name can only contain letters, numbers, underscore or hyphen")

        action = request.form.get('action')
        # --- JOIN FLIGHT LOGIC ---
        if action == 'Join Flight' and mission_id and callsign_prefix and desired_slot:
            print(f"[DEBUG] Join Flight action received: {callsign_prefix}, slot {desired_slot}")
            
            if not aircraft_tail:
                raise ValueError("Aircraft must be selected")
                
            try:
                desired_slot = int(desired_slot)
                if desired_slot < 2 or desired_slot > 4:
                    raise ValueError()
            except ValueError:
                raise ValueError("Invalid slot number. Must be between 2 and 4")
            
            # Get pilot name or use default
            pilot_name = request.form.get('pilot_name', '')
            if not pilot_name:
                # Generate a default pilot name if none provided
                pilot_name = f"WINGMAN{desired_slot}"
                
            # Prepare flight data for joining
            flight_data = {
                "aircraft": aircraft_tail,
                "callsign_prefix": callsign_prefix,
                "desired_slot": desired_slot,
                "pilot_name": pilot_name
            }
                
            success, result = mission_manager.add_flight(mission_id, flight_data)
            
            if not success:
                raise ValueError(f"Failed to join flight: {result}")
                
            print(f"[DEBUG] Successfully joined flight: {callsign_prefix} as #{desired_slot}")
            # Redirect to the main page with success message
            return render_template('index.html',
                missions=mission_manager.get_all_missions(),
                base_info=base_data,
                available_bases=available_bases if 'available_bases' in locals() else [],
                selected_mission_id=mission_id,
                success_message=f"Successfully joined flight {callsign_prefix} as #{desired_slot}"
            )

        # --- CREATE NEW FLIGHT LOGIC ---
        if action == 'File Flight Plan' and mission_id and not (callsign_prefix and desired_slot):
            print(f"[DEBUG] File Flight Plan action received with data: {request.form}")
            
            # Only for new flight leads, not join
            if not (squadron and dep_base and aircraft_tail and dep_type and dep_proc and area and rec_base and rec_type and rec_proc):
                missing = []
                if not squadron: missing.append("squadron")
                if not dep_base: missing.append("departure base")
                if not aircraft_tail: missing.append("aircraft")
                if not dep_type: missing.append("departure type")
                if not dep_proc: missing.append("departure procedure")
                if not area: missing.append("training area")
                if not rec_base: missing.append("recovery base")
                if not rec_type: missing.append("recovery type")
                if not rec_proc: missing.append("recovery procedure")
                
                error_msg = f"Missing required fields: {', '.join(missing)}"
                print(f"[ERROR] {error_msg}")
                raise ValueError(error_msg)
            
            route = get_route(dep_base, dep_proc, area, rec_proc, rec_base, squadron)
            if not route:
                raise ValueError("Failed to generate route")
                
            # Get pilot name or use default
            pilot_name = request.form.get('pilot_name', '')
            if not pilot_name:
                pilot_name = "LEAD"
                
            # Get intentions (optional)
            intentions = request.form.get('intentions', '').strip()
            
            print(f"[DEBUG] Creating flight with: squadron={squadron}, aircraft={aircraft_tail}, type={aircraft_data[aircraft_tail]['type']}")
                
            flight_data = {
                "squadron": squadron,
                "aircraft": aircraft_tail,
                "aircraft_type": aircraft_data[aircraft_tail]["type"],
                "area": area,
                "route": route.split('\n')[1] if '\n' in route else route,
                "departure": {
                    "base": dep_base,
                    "type": dep_type,
                    "runway": base_data[dep_base]["runway_in_use"],
                    "procedure": dep_proc
                },
                "recovery": {
                    "base": rec_base,
                    "type": rec_type,
                    "runway": base_data[rec_base]["runway_in_use"],
                    "procedure": rec_proc
                },
                "intentions": intentions,
                "pilot_name": pilot_name
            }
            
            print(f"[DEBUG] Flight data being sent to mission_manager: {flight_data}")
            success, result = mission_manager.add_flight(mission_id, flight_data)
            
            if not success:
                error_msg = f"Failed to add flight: {result}"
                print(f"[ERROR] {error_msg}")
                raise ValueError(error_msg)
                
            print(f"[DEBUG] Flight created successfully: {result['callsign']}")
            return render_template('index.html',
                missions=mission_manager.get_all_missions(),
                base_info=base_data,
                available_bases=available_bases,
                selected_mission_id=mission_id,
                success_message=f"Flight plan filed successfully: {result['callsign']}"
            )

        # Handle AJAX responses
        if is_ajax:
            response_data = {
                'options': {},
                'output': '',
                'form_data': None
            }

            # If joining an existing flight, only show aircraft selection (limit to squadron/base of lead)
            if mission_id and callsign_prefix and desired_slot and lead_flight:
                selected_aircraft = get_available_aircraft(current_mission, lead_flight['squadron'], lead_flight['departure']['base'], lead_flight)
                response_data['options']['aircraft'] = ''.join([
                    '<option value="">Select Aircraft</option>'
                ] + [
                    f'<option value="{tail}">{tail}</option>' for tail in selected_aircraft
                ])
                response_data['form_data'] = {
                    'selected_mission_id': mission_id,
                    'callsign_prefix': callsign_prefix,
                    'desired_slot': desired_slot,
                    'selected_flight_data': lead_flight,
                    'aircraft_data': aircraft_data,
                    'selected_aircraft': selected_aircraft,
                    'selected_aircraft_tail': aircraft_tail
                }
                return jsonify(response_data)

            # Ensure all required options are populated when a mission is selected
            if mission_id:
                response_data['options']['aircraft'] = ''.join([
                    '<option value="">Select Aircraft</option>'
                ] + [
                    f'<option value="{tail}">{tail}</option>' for tail in selected_aircraft
                ])

                response_data['options']['dep_base'] = ''.join([
                    '<option value="">Select Base</option>'
                ] + [
                    f'<option value="{base}">{base}</option>' for base in available_bases
                ])

                response_data['options']['rec_base'] = ''.join([
                    '<option value="">Select Base</option>'
                ] + [
                    f'<option value="{base}">{base}</option>' for base in all_bases
                ])

                response_data['options']['dep_type'] = ''.join([
                    '<option value="">Select Type</option>',
                    '<option value="VFR">VFR</option>',
                    '<option value="IFR">IFR</option>'
                ])

                response_data['options']['rec_type'] = ''.join([
                    '<option value="">Select Type</option>',
                    '<option value="VFR">VFR</option>',
                    '<option value="IFR">IFR</option>'
                ])

                response_data['options']['training_area'] = ''.join([
                    '<option value="">Select Training Area</option>'
                ] + [
                    f'<option value="{area}">{area}</option>' for area in area_list
                ])

            # If mission was just selected, include form data for rendering
            if mission_id:
                response_data['form_data'] = {
                    'selected_mission_id': mission_id,
                    'selected_flight': selected_flight,
                    'selected_flight_data': lead_flight,
                    'aircraft_data': aircraft_data,
                    'available_flights': available_flights,
                    'squadrons': sorted(squadron_data.keys()),
                    'selected_aircraft': selected_aircraft,
                    'selected_aircraft_tail': aircraft_tail,
                    'dep_procs': dep_procs,
                    'rec_procs': rec_procs,
                    'selected_squadron': squadron,
                    'selected_base': dep_base,
                    'selected_rec_base': rec_base,
                    'selected_dep_type': dep_type,
                    'selected_rec_type': rec_type,
                    'selected_dep_proc': dep_proc,
                    'selected_rec_proc': rec_proc,
                    'area_list': area_list,
                    'selected_area': area,
                    'base_info': base_data,
                    'available_bases': available_bases,
                    'mission': current_mission
                }

            return jsonify(response_data)

        response_data = {
            'options': {},
            'output': ''
        }

        # Get available choices based on selections
        selected_aircraft = []
        available_bases = get_squadron_bases(squadron) if squadron else []
        all_bases = sorted(base_data.keys())  # Get all bases for recovery
        
        # Debug what's happening with squadron selection
        print(f"[DEBUG] Squadron selected: {squadron}")
        print(f"[DEBUG] Available bases for squadron: {available_bases}")
        
        # If squadron is selected, update base dropdowns - DIRECTLY ADD OPTIONS HERE
        if squadron:
            # Get squadron bases first
            available_bases = get_squadron_bases(squadron)
            print(f"[DEBUG] Populating dep_base dropdown with: {available_bases}")
            
            # Departure base - only bases where squadron has aircraft
            dep_base_options = [
                '<option value="">Select Base</option>'
            ]
            for base in available_bases:
                dep_base_options.append(
                    f'<option value="{base}"{" selected" if base == dep_base else ""}>{base}</option>'
                )
            response_data['options']['dep_base'] = ''.join(dep_base_options)
            
            # Recovery base - all bases
            rec_base_options = [
                '<option value="">Select Base</option>'
            ]
            for base in all_bases:
                rec_base_options.append(
                    f'<option value="{base}"{" selected" if base == rec_base else ""}>{base}</option>'
                )
            response_data['options']['rec_base'] = ''.join(rec_base_options)

        # If departure base is selected, update aircraft and dep_type
        if squadron and dep_base:
            print(f"[DEBUG] Squadron and base selected: {squadron}, {dep_base}")
            
            # Get aircraft based on squadron and base
            selected_aircraft = [
                tail for tail, meta in aircraft_data.items()
                if meta.get('squadron') == squadron and meta.get('base') == dep_base
            ]
            print(f"[DEBUG] Available aircraft: {selected_aircraft}")
            
            # Update aircraft dropdown
            aircraft_options = [
                '<option value="">Select Aircraft</option>'
            ]
            for tail in selected_aircraft:
                aircraft_options.append(
                    f'<option value="{tail}"{" selected" if tail == aircraft_tail else ""}>{tail}</option>'
                )
            response_data['options']['aircraft'] = ''.join(aircraft_options)
            
            # Update departure type dropdown
            response_data['options']['dep_type'] = ''.join([
                '<option value="">Select Type</option>',
                f'<option value="VFR"{" selected" if dep_type == "VFR" else ""}>VFR</option>',
                f'<option value="IFR"{" selected" if dep_type == "IFR" else ""}>IFR</option>'
            ])

        # If recovery base is selected, update recovery type dropdown
        if rec_base:
            response_data['options']['rec_type'] = ''.join([
                '<option value="">Select Type</option>',
                f'<option value="VFR"{" selected" if rec_type == "VFR" else ""}>VFR</option>',
                f'<option value="IFR"{" selected" if rec_type == "IFR" else ""}>IFR</option>'
            ])

        # Get departure procedures
        if dep_base and dep_type:
            dep_proc_groups = get_procedures(dep_base, 'dep', base_data.get(dep_base, {}), dep_type)
            response_data['options']['dep_proc'] = ''.join([
                f'<option value="">Select Procedure</option>'
            ] + [
                f'<optgroup label="{group}">' +
                ''.join([
                    f'<option value="{proc.replace("→ ", "")}" {"selected" if proc.replace("→ ", "") == dep_proc else ""}>{proc}</option>'
                    for proc in procs
                ]) +
                '</optgroup>'
                for group, procs in dep_proc_groups
            ])

        # Get recovery procedures
        if rec_base and rec_type:
            rec_proc_groups = get_procedures(rec_base, 'rec', base_data.get(rec_base, {}), rec_type)
            response_data['options']['rec_proc'] = ''.join([
                f'<option value="">Select Procedure</option>'
            ] + [
                f'<optgroup label="{group}">' +
                ''.join([
                    f'<option value="{proc.replace("→ ", "")}" {"selected" if proc.replace("→ ", "") == rec_proc else ""}>{proc}</option>'
                    for proc in procs
                ]) +
                '</optgroup>'
                for group, procs in rec_proc_groups
            ])

        # Update training area dropdown if we're handling an AJAX request
        if is_ajax:
            area_options = ['<option value="">Select Training Area</option>']
            for area_name in area_list:
                area_options.append(
                    f'<option value="{area_name}"{" selected" if area_name == area else ""}>{area_name}</option>'
                )
            response_data['options']['training_area'] = ''.join(area_options)

        # Generate route if we have all required fields
        if all([dep_base, dep_proc, area, rec_proc, rec_base]):
            route = get_route(dep_base, dep_proc, area, rec_proc, rec_base, squadron)
            if route:
                output = f'<div class="route-preview">{route}</div>'
                route_preview = True
                if is_ajax:
                    response_data['output'] = output
                    # When showing preview, also send back all current selections to maintain state
                    response_data['selections'] = {
                        'dep_type': dep_type,
                        'dep_proc': dep_proc,
                        'rec_type': rec_type,
                        'rec_proc': rec_proc,
                        'rec_base': rec_base
                    }

        if is_ajax:
            return jsonify(response_data)

        return render_template('index.html',
            missions=mission_manager.get_all_missions(),
            base_info=base_data,
            available_bases=available_bases,
            selected_mission_id=mission_id,
            selected_flight=selected_flight,
            selected_flight_data=lead_flight if selected_flight else None,
            aircraft_data=aircraft_data,
            available_flights=available_flights,
            squadrons=sorted(squadron_data.keys()),
            selected_aircraft=selected_aircraft,
            selected_aircraft_tail=aircraft_tail,
            dep_procs=[p.replace("→ ", "") for group, procs in (get_procedures(dep_base, 'dep', base_data.get(dep_base, {}), dep_type) if dep_base and dep_type else []) for p in procs],
            rec_procs=[p.replace("→ ", "") for group, procs in (get_procedures(rec_base, 'rec', base_data.get(rec_base, {}), rec_type) if rec_base and rec_type else []) for p in procs],
            selected_squadron=squadron,
            selected_base=dep_base,
            selected_rec_base=rec_base,
            selected_dep_type=dep_type,
            selected_rec_type=rec_type,
            selected_dep_proc=dep_proc,
            selected_rec_proc=rec_proc,
            area_list=area_list,
            selected_area=area,
            output=output,
            route_preview=route_preview)
    except Exception as e:
        print(f"[ERROR] {str(e)}")
        if is_ajax:
            return jsonify({'error': str(e)})
        
        # Make sure we pass all required template variables even in error case
        return render_template('index.html',
            error=str(e),
            missions=mission_manager.get_all_missions(),
            base_info=base_data,
            available_bases=[],
            selected_mission_id='',
            selected_flight='',
            selected_flight_data=None,
            aircraft_data=aircraft_data,
            available_flights=[],
            squadrons=sorted(squadron_data.keys()),
            selected_aircraft=[],
            selected_aircraft_tail='',
            dep_procs=[],
            rec_procs=[],
            selected_squadron='',
            selected_base='',
            selected_rec_base='',
            selected_dep_type='',
            selected_rec_type='',
            selected_dep_proc='',
            selected_rec_proc='',
            area_list=[],
            selected_area='',
            output='',
            route_preview=False
        )

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

if __name__ == '__main__':
    print("[INIT] Starting Flask app")
    # Configuration for Gunicorn production server
    # This app is intended to be run behind Nginx with Gunicorn
    # Command to run: gunicorn -w 4 -b 127.0.0.1:8000 app:app
    
    # For development only - do not use in production
    app.run(debug=False, host='127.0.0.1', port=8000)
