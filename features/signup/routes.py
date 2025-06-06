from flask import render_template, redirect, url_for, request, current_app, flash, session, jsonify
from . import signup_bp
import logging
import requests
import re
import uuid
from datetime import datetime
from utils.storage import load_mission, load_campaign, save_mission
from features.missions.routes import storage_list_missions
from utils.auth import login_required
from models.flight import (create_flight, get_flight, get_mission_flights_data,
                          join_flight, leave_flight, delete_flight)
from utils.resources import (get_squadrons, get_bases, get_operations_areas, get_aircraft_at_base, get_squadron_aircraft, get_callsign)
import os
import json

logger = logging.getLogger(__name__)

def format_nickname(nick):
    """Capitalize and remove Discord tags from nickname for display."""
    if not nick:
        return ''
    import re
    clean = re.sub(r'#\d{4,}$', '', nick).strip()
    if clean:
        clean = clean[0].upper() + clean[1:]
    return clean

# Register as Jinja filter
signup_bp.add_app_template_filter(format_nickname, 'format_nickname')

@signup_bp.route("/")
@login_required
def dashboard():
    """Main dashboard showing available missions and flights"""
    # Get discord client from current_app
    discord = current_app.discord
    
    # Get Discord user
    user = discord.fetch_user()
    user_id = user.id
    
    # Fetch roles from your bot API
    try:
        logger.debug(f"Fetching roles and nickname for user ID {user_id}")
        resp = requests.get(
            f"{current_app.config['BOT_API_URL']}/roles/{user_id}", timeout=2
        )
        resp.raise_for_status()
        response_data = resp.json()
        user_roles = response_data.get("roles", [])
        
        # Try to get nickname from bot API if available
        nickname = response_data.get("nickname", user.username)
        # Remove text within square brackets or parentheses and strip
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', nickname).strip()
        # Make the whole name uppercase
        display_name = clean_name.upper()
        logger.debug(f"Final display name: '{display_name}'")
    except Exception as e:
        logger.error(f"Could not fetch roles from bot: {e}")
        user_roles = []
        nickname = user.username
        # Remove text within square brackets or parentheses and strip
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', nickname).strip()
        # Make the whole name uppercase
        display_name = clean_name.upper()
        logger.debug(f"Using Discord username as fallback: '{display_name}'")
        
    # Get config from current app
    app = current_app
    
    # Check for admin role
    admin_role = app.config.get("ADMIN_ROLE")
    is_admin = any(role['id'] == admin_role for role in user_roles)
    
    # You can add more role checks as needed
    mission_maker_role = app.config.get("MISSION_MAKER_ROLE", "")
    red_team_role = app.config.get("RED_TEAM_ROLE", "")
    blue_team_role = app.config.get("BLUE_TEAM_ROLE", "")
    is_mission_maker = any(role['id'] == mission_maker_role for role in user_roles)
    has_red_role = any(role['id'] == red_team_role for role in user_roles)
    has_blue_role = any(role['id'] == blue_team_role for role in user_roles)
    
    # Fetch available missions for signup
    missions = storage_list_missions()
    
    return render_template(
        "signup_home.html",
        user=user,
        display_name=display_name,
        user_roles=user_roles,
        is_admin=is_admin,
        is_mission_maker=is_mission_maker,
        admin_role=admin_role,
        red_team_role=red_team_role,
        blue_team_role=blue_team_role,
        has_red_role=has_red_role,
        has_blue_role=has_blue_role,
        missions=missions,
        current_year=datetime.now().year,
        is_authenticated=True
    )

@signup_bp.route("/mission/<mission_id>")
@login_required
def signup_mission(mission_id):
    """Mission-specific signup page"""
    # Get Discord user info
    discord = current_app.discord
    user = discord.fetch_user()
    user_id = str(user.id)
    
    # Get roles and nickname
    try:
        resp = requests.get(
            f"{current_app.config['BOT_API_URL']}/roles/{user_id}", timeout=2
        )
        resp.raise_for_status()
        response_data = resp.json()
        user_roles = response_data.get("roles", [])
        nickname = response_data.get("nickname", user.username)
        # Remove text within square brackets or parentheses and strip
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', nickname).strip()
        # Make the whole name uppercase
        display_name = clean_name.upper()
    except Exception as e:
        logger.error(f"Could not fetch roles from bot: {e}")
        user_roles = []
        nickname = user.username
        # Remove text within square brackets or parentheses and strip
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', nickname).strip()
        # Make the whole name uppercase
        display_name = clean_name.upper()
    
    # Get mission details
    mission = load_mission(mission_id)
    if not mission:
        flash("Mission not found", "danger")
        return redirect(url_for("signup.dashboard"))
    
    # Load campaign and persistent_ac_location
    campaign = None
    persistent_ac_location = False
    campaign_id = mission.get("campaign_id")
    campaign_type = None
    if campaign_id:
        campaign = load_campaign(campaign_id)
        if campaign:
            persistent_ac_location = campaign.get("persistent_ac_location", False)
            campaign_type = campaign.get("type", "EX")  # Default to EX if not specified
    
    # Get all flights for this mission
    flights = get_mission_flights_data(mission_id)

    # Role logic for filtering
    admin_role = current_app.config.get("ADMIN_ROLE")
    mission_maker_role = current_app.config.get("MISSION_MAKER_ROLE", "")
    red_team_role = current_app.config.get("RED_TEAM_ROLE", "")
    blue_team_role = current_app.config.get("BLUE_TEAM_ROLE", "")
    user_role_ids = [role['id'] for role in user_roles]
    is_admin = admin_role in user_role_ids
    is_mission_maker = mission_maker_role in user_role_ids
    is_red = red_team_role in user_role_ids
    is_blue = blue_team_role in user_role_ids

    # Filter flights by side for non-admin/mission maker
    if not (is_admin or is_mission_maker):
        if is_red:
            flights = [f for f in flights if getattr(f, 'side', None) == 'red']
        elif is_blue:
            flights = [f for f in flights if getattr(f, 'side', None) == 'blue']
        else:
            flights = []

    # Get resources for flight creation - using enhanced squadron system
    from utils.squadron_manager import squadron_manager
    
    # Load squadrons specific to the current mission's campaign
    mission_campaign_id = mission.get("campaign_id") if mission else None
    if mission_campaign_id and campaign and "squadrons" in campaign and campaign["squadrons"]:
        squadrons = squadron_manager.get_campaign_squadrons(mission_campaign_id, campaign["squadrons"])
        logger.info(f"[SIGNUP] Using campaign squadrons dict for campaign {mission_campaign_id}")
    else:
        squadrons = {}
        logger.info(f"[SIGNUP] Using fallback squadron loading (no campaign or campaign squadrons)")
    
    bases = get_bases(campaign_id)
    operations_areas = get_operations_areas()

    # Load mission types from instance/data/mission_types.json (fix path)
    mission_types_path = os.path.join(current_app.instance_path, "data", "mission_types.json")
    logger.info(f"[MISSION_TYPES] Using mission_types_path: {mission_types_path}")
    if not os.path.isfile(mission_types_path):
        logger.error(f"[MISSION_TYPES] File does not exist: {mission_types_path}")
        flash(f"mission_types.json not found at {mission_types_path}", "danger")
        mission_types = {}
    else:
        try:
            # Use cached loading for better performance
            from utils.cache import get_cached_json
            mission_types = get_cached_json(mission_types_path)  # Pass the full dict, not just keys
            if not mission_types:
                logger.warning(f"[MISSION_TYPES] mission_types.json is empty!")
                flash("No mission types loaded! Check mission_types.json and file permissions.", "danger")
        except Exception as e:
            logger.error(f"Could not load mission_types.json: {e}")
            flash("Error loading mission_types.json. See logs for details.", "danger")
            mission_types = {}

    # Check user's current flight (if any)
    user_flight = None
    user_position = None
    for flight in flights:
        for pilot in flight.pilots:
            # EMERGENCY FIX: Handle both old and new data formats safely
            # Some pilot records may not have user_id field (old format)
            pilot_user_id = pilot.get("user_id")
            pilot_username = pilot.get("username")
            
            # Check both user_id (new format) and username (old format compatibility)
            if pilot_user_id == user_id or pilot_username == user.username:
                user_flight = flight
                user_position = pilot.get("position")
                break
        if user_flight:
            break

    # Load aircraft data for JS dropdowns
    from utils.resources import get_resources
    aircraft_data = get_resources().get("aircraft", {})

    # Render the signup page
    return render_template(
        "signup_mission.html",
        mission=mission,
        flights=flights,
        user=user,
        user_id=user_id,
        display_name=display_name,
        user_flight=user_flight,
        user_position=user_position,
        squadrons=squadrons,
        bases=bases,
        operations_areas=operations_areas,
        mission_types=mission_types,
        aircraft_data=aircraft_data,
        current_year=datetime.now().year,
        is_authenticated=True,
        persistent_ac_location=persistent_ac_location,
        is_admin=is_admin,
        is_mission_maker=is_mission_maker,
        campaign_type=campaign_type,
        campaign_id=campaign_id  # <-- Ensure campaign_id is always passed to template
    )

@signup_bp.route("/process_signup/<mission_id>", methods=["POST"])
@login_required
def process_signup(mission_id):
    """Process mission signup form submission"""
    from utils.storage import load_mission, save_mission
    
    # Get form data
    coalition = request.form.get('coalition')
    aircraft = request.form.get('aircraft')
    
    if not coalition or not aircraft:
        flash("Please select both a coalition and an aircraft.", "warning")
        return redirect(url_for("signup.signup_mission", mission_id=mission_id))
    
    # Get Discord user info
    discord = current_app.discord
    user = discord.fetch_user()
    user_id = user.id
    
    # Get nickname
    try:
        resp = requests.get(
            f"{current_app.config['BOT_API_URL']}/roles/{user_id}", timeout=2
        )
        resp.raise_for_status()
        response_data = resp.json()
        nickname = response_data.get("nickname", user.username)
        # Remove text within square brackets or parentheses and strip
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', nickname).strip()
        # Make the whole name uppercase
        display_name = clean_name.upper()
    except Exception as e:
        logger.error(f"Could not fetch nickname from bot: {e}")
        nickname = user.username
        # Remove text within square brackets or parentheses and strip
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', nickname).strip()
        # Make the whole name uppercase
        display_name = clean_name.upper()
    
    # Load mission data
    mission = load_mission(mission_id)
    if not mission:
        flash("Mission not found.", "danger")
        return redirect(url_for("signup.dashboard"))
    
    # Initialize signups list if it doesn't exist
    if "signups" not in mission:
        mission["signups"] = []
    
    # Check if user already signed up
    for signup in mission["signups"]:
        if signup.get("user_id") == str(user_id):
            # Update existing signup
            signup["coalition"] = coalition
            signup["aircraft"] = aircraft
            signup["status"] = "Pending"  # Reset status for changed signup
            flash("Your signup has been updated.", "success")
            save_mission(mission)
            return redirect(url_for("signup.signup_mission", mission_id=mission_id))
    
    # Create new signup entry
    new_signup = {
        "user_id": str(user_id),
        "pilot": display_name,
        "coalition": coalition,
        "aircraft": aircraft,
        "status": "Pending",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    mission["signups"].append(new_signup)
    save_mission(mission)
    
    flash("You have successfully signed up for this mission.", "success")
    return redirect(url_for("signup.signup_mission", mission_id=mission_id))

@signup_bp.route("/mission/<mission_id>/create_flight", methods=["POST"])
@login_required
def create_new_flight(mission_id):
    """Create a new flight for a mission"""
    # Get Discord user info
    discord = current_app.discord
    user = discord.fetch_user()
    user_id = str(user.id)
    # Use display_name for all flight creation/joining
    try:
        resp = requests.get(
            f"{current_app.config['BOT_API_URL']}/roles/{user_id}", timeout=2
        )
        resp.raise_for_status()
        response_data = resp.json()
        nickname = response_data.get("nickname", user.username)
        user_roles = response_data.get("roles", [])
        # Remove text within square brackets or parentheses and strip
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', nickname).strip()
        # Make the whole name uppercase
        display_name = clean_name.upper()
    except Exception as e:
        logger.error(f"Could not fetch nickname from bot: {e}")
        nickname = user.username
        user_roles = []
        # Remove text within square brackets or parentheses and strip
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', nickname).strip()
        display_name = clean_name.upper()
    username = display_name

    # Get role config
    admin_role = current_app.config.get("ADMIN_ROLE")
    mission_maker_role = current_app.config.get("MISSION_MAKER_ROLE", "")
    red_team_role = current_app.config.get("RED_TEAM_ROLE", "")
    blue_team_role = current_app.config.get("BLUE_TEAM_ROLE", "")
    user_role_ids = [role['id'] for role in user_roles]
    is_admin = admin_role in user_role_ids
    is_mission_maker = mission_maker_role in user_role_ids
    is_red = red_team_role in user_role_ids
    is_blue = blue_team_role in user_role_ids

    # Get form data
    squadron = request.form.get("squadron")
    departure_base = request.form.get("departure_base")
    recovery_base = request.form.get("recovery_base")
    operations_area = request.form.get("operations_area")
    mission_type = request.form.get("mission_type")
    remarks = request.form.get("remarks")
    aircraft_id = request.form.get("aircraft_id")
    # Determine side
    side = None
    if is_admin or is_mission_maker:
        # Allow admin/mission maker to pick side from form (if present)
        side = request.form.get("side")
        if side not in ("red", "blue"):
            # fallback: default to blue if not specified
            side = "blue"
    elif is_red:
        side = "red"
    elif is_blue:
        side = "blue"
    else:
        # fallback: default to blue if user has no team role
        side = "blue"
    logger.debug(f"[CREATE_NEW_FLIGHT] Assigned side: {side}")

    # Enforce Persistent A/C Location rule
    mission = load_mission(mission_id)
    campaign_id = mission.get("campaign_id") if mission else None
    persistent_ac_location = False
    if campaign_id:
        campaign = load_campaign(campaign_id)
        if campaign:
            persistent_ac_location = campaign.get("persistent_ac_location", False)
    if persistent_ac_location:
        # Only allow aircraft at their current location
        from utils.resources import get_resources
        resources = get_resources()
        aircraft_data = resources.get("aircraft", {})
        aircraft_meta = aircraft_data.get(aircraft_id, {})
        aircraft_location = aircraft_meta.get("location")
        if not aircraft_location or aircraft_location != departure_base:
            flash("Persistent A/C Location is enabled: You can only select aircraft at their current base.", "danger")
            logger.warning(f"[CREATE_NEW_FLIGHT] Attempted to create flight with aircraft {aircraft_id} at {departure_base}, but its location is {aircraft_location}.")
            return redirect(url_for("signup.signup_mission", mission_id=mission_id))
    else:
        # If not persistent, allow any aircraft from the squadron at any base
        # No restriction: skip location check
        pass

    # Validate required fields (remarks is optional)
    if not all([squadron, departure_base, recovery_base, operations_area, mission_type, aircraft_id]):
        flash("All fields except remarks are required", "danger")
        logger.error(f"[CREATE_NEW_FLIGHT] Missing required fields.")
        return redirect(url_for("signup.signup_mission", mission_id=mission_id))
    
    # Create the flight
    flight_data = {
        "squadron": squadron,
        "departure_base": departure_base,
        "recovery_base": recovery_base,
        "operations_area": operations_area,
        "mission_type": mission_type,
        "remarks": remarks,
        "aircraft_id": aircraft_id,
        "side": side
    }
    try:
        flight = create_flight(mission_id, flight_data, user_id, username)
        flash(f"Flight {flight.callsign} {flight.flight_number} created successfully", "success")
    except Exception as e:
        import traceback
        logger.error(f"[CREATE_NEW_FLIGHT] Failed to create flight: {e}\n{traceback.format_exc()}")
        flash(f"Failed to create flight: {e}", "danger")
    
    return redirect(url_for("signup.signup_mission", mission_id=mission_id))

@signup_bp.route("/mission/<mission_id>/join_flight/<flight_id>", methods=["POST"])
@login_required
def join_existing_flight(mission_id, flight_id):
    logger.debug(f"[JOIN_FLIGHT] Received mission_id={mission_id}, flight_id={flight_id}")
    discord = current_app.discord
    user = discord.fetch_user()
    user_id = str(user.id)
    try:
        resp = requests.get(
            f"{current_app.config['BOT_API_URL']}/roles/{user_id}", timeout=2
        )
        resp.raise_for_status()
        response_data = resp.json()
        nickname = response_data.get("nickname", user.username)
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', nickname).strip()
        display_name = clean_name.upper()
    except Exception as e:
        logger.error(f"Could not fetch nickname from bot: {e}")
        nickname = user.username
        clean_name = re.sub(r'\[.*?\]|\(.*?\)', '', nickname).strip()
        display_name = clean_name.upper()
    username = display_name

    position = request.form.get("position") or request.values.get("position")
    aircraft = request.form.get("aircraft_id") or request.form.get("aircraft") or request.values.get("aircraft_id") or request.values.get("aircraft")
    logger.debug(f"[JOIN_FLIGHT] Received position={position}, aircraft={aircraft}")
    if not position or position not in ["2", "3", "4"]:
        flash("Invalid position selected", "danger")
        return redirect(url_for("signup.signup_mission", mission_id=mission_id))
    if not aircraft:
        flash("Aircraft must be selected", "danger")
        return redirect(url_for("signup.signup_mission", mission_id=mission_id))

    # Extra debug: log available flight IDs in mission
    from utils.storage import load_mission
    mission = load_mission(mission_id)
    if mission and "flights" in mission:
        logger.debug(f"[JOIN_FLIGHT] Available flight IDs: {list(mission['flights'].keys())}")
    else:
        logger.debug(f"[JOIN_FLIGHT] No flights found in mission {mission_id}")

    flight, message = join_flight(flight_id, user_id, username, position, mission_id, aircraft)
    if flight:
        flash(f"Successfully joined flight {flight.callsign} {flight.flight_number} as #{position}", "success")
    else:
        flash(message, "danger")
    return redirect(url_for("signup.signup_mission", mission_id=mission_id))

@signup_bp.route("/mission/<mission_id>/leave_flight/<flight_id>", methods=["POST"])
@login_required
def leave_existing_flight(mission_id, flight_id):
    """Leave a flight"""
    # Get Discord user info
    discord = current_app.discord
    user = discord.fetch_user()
    user_id = str(user.id)
    
    # Leave the flight
    flight, message = leave_flight(flight_id, user_id, mission_id)
    flash(message, "info")
    
    return redirect(url_for("signup.signup_mission", mission_id=mission_id))

@signup_bp.route("/get_aircraft", methods=["GET"])
@login_required
def get_base_aircraft():
    """API endpoint to get aircraft available at a selected base"""
    base_id = request.args.get("base_id")
    squadron = request.args.get("squadron")
    campaign_id = request.args.get("campaign_id")  # Add campaign_id parameter
    
    if not base_id:
        return jsonify({"error": "Base ID required"}), 400
    
    # Get aircraft at the base - use campaign-specific aircraft state if available
    from utils.resources import get_aircraft_at_base
    aircraft = get_aircraft_at_base(base_id, campaign_id)
    
    # Filter by squadron if provided
    if squadron:
        aircraft = {
            tail: data for tail, data in aircraft.items()
            if data.get("squadron") == squadron
        }
    
    return jsonify({"aircraft": aircraft})

@signup_bp.route("/squadron-bases", methods=["POST"])
@login_required
def squadron_bases_endpoint():
    """Return a list of bases for a given squadron (AJAX)"""
    squadron = request.form.get("squadron")
    persistent = request.form.get("persistent", "1") == "1"
    campaign_id = request.form.get("campaign_id")
    bases = get_bases(campaign_id)
    base_ids = []
    if persistent and campaign_id:
        # Only show bases where this squadron has aircraft in campaign squadrons.json
        aircraft = get_squadron_aircraft(squadron, None, campaign_id)
        found_bases = set()
        for ac in aircraft.values():
            loc = ac.get("location")
            if loc:
                found_bases.add(loc)
        base_ids = list(found_bases)
        logger.debug(f"[SQUADRON BASES ENDPOINT] squadron={squadron}, persistent={persistent}, campaign_id={campaign_id}, aircraft={aircraft}, found_bases={found_bases}, bases_dict_keys={list(bases.keys())}, base_ids={base_ids}")
    else:
        base_ids = list(bases.keys())
        logger.debug(f"[SQUADRON BASES ENDPOINT] squadron={squadron}, persistent={persistent}, campaign_id={campaign_id}, bases_dict_keys={list(bases.keys())}, base_ids={base_ids}")
    return jsonify({"bases": base_ids})

@signup_bp.route("/squadron-aircraft", methods=["POST"])
@login_required
def squadron_aircraft_endpoint():
    """Return a list of aircraft for a given squadron and base (AJAX)"""
    squadron = request.form.get("squadron")
    base = request.form.get("base")
    persistent = request.form.get("persistent", "1") == "1"
    mission_id = request.form.get("mission_id")
    campaign_id = request.form.get("campaign_id")
    mode = request.form.get("mode", "lead")
    in_use_aircraft = set()
    if mission_id:
        from models.flight import get_mission_flights_data
        flights = get_mission_flights_data(mission_id)
        for flight in flights:
            for pilot in flight.pilots:
                if pilot.get("aircraft"):
                    in_use_aircraft.add(str(pilot["aircraft"]))
    aircraft_info = []
    if mode == "lead":
        if persistent and base:
            all_aircraft = get_squadron_aircraft(squadron, base, campaign_id)
        else:
            all_aircraft = get_squadron_aircraft(squadron, None, campaign_id)
        for tail, data in all_aircraft.items():
            if str(tail) not in in_use_aircraft:
                aircraft_info.append({
                    "tail": str(tail),
                    "type": data.get("type", ""),
                    "location": data.get("location", "")
                })
    elif mode == "wingman":
        all_aircraft = get_squadron_aircraft(squadron, None, campaign_id)
        for tail, data in all_aircraft.items():
            if str(tail) not in in_use_aircraft:
                aircraft_info.append({
                    "tail": str(tail),
                    "type": data.get("type", ""),
                    "location": data.get("location", "")
                })
    else:
        if persistent and base:
            all_aircraft = get_squadron_aircraft(squadron, base, campaign_id)
        else:
            all_aircraft = get_squadron_aircraft(squadron, None, campaign_id)
        for tail, data in all_aircraft.items():
            if str(tail) not in in_use_aircraft:
                aircraft_info.append({
                    "tail": str(tail),
                    "type": data.get("type", ""),
                    "location": data.get("location", "")
                })
    logger.debug(f"[SQUADRON AIRCRAFT ENDPOINT] mode={mode}, squadron={squadron}, base={base}, persistent={persistent}, campaign_id={campaign_id}, aircraft_info={aircraft_info}")
    return jsonify({"aircraft": aircraft_info})


@signup_bp.route("/mission/<mission_id>/claim_curated_slot/<int:slot_idx>", methods=["POST"])
@login_required
def claim_curated_slot(mission_id, slot_idx):
    """Claim a curated slot and convert it into a real flight"""
    current_user = session.get("username")
    if not current_user:
        flash("You must be logged in to claim a slot.", "danger")
        return redirect(url_for("auth.login"))
    
    logger.info(f"[SIGNUP] User {current_user} attempting to claim slot {slot_idx} in mission {mission_id}")
    
    # Load the mission
    mission = load_mission(mission_id)
    if not mission:
        flash("Mission not found.", "danger")
        return redirect(url_for("signup.dashboard"))
    
    # Validate slot index
    curated_slots = mission.get("curated_slots", [])
    if slot_idx < 0 or slot_idx >= len(curated_slots):
        flash("Invalid slot index.", "danger")
        logger.warning(f"[SIGNUP] Invalid slot index {slot_idx} for mission {mission_id}")
        return redirect(url_for("signup.signup_mission", mission_id=mission_id))
    
    # Get the curated slot to claim
    slot_to_claim = curated_slots[slot_idx]
    
    # Get form data for additional flight details
    squadron = request.form.get("squadron")
    departure_base = request.form.get("departure_base")
    recovery_base = request.form.get("recovery_base")
    operations_area = request.form.get("operations_area")
    aircraft_id = request.form.get("aircraft_id")
    remarks = request.form.get("remarks", "")
    
    if not squadron or not departure_base or not operations_area or not aircraft_id:
        flash("Please fill in all required fields.", "danger")
        return redirect(url_for("signup.signup_mission", mission_id=mission_id))
    
    # Validate that the selected squadron is allowed for this slot
    if squadron not in slot_to_claim.get("squadrons", []):
        flash("Invalid squadron selection for this slot.", "danger")
        return redirect(url_for("signup.signup_mission", mission_id=mission_id))
    
    # Get campaign_id from mission for callsign assignment
    campaign_id = mission.get("campaign_id")
    try:
        # Create new flight from curated slot
        flight_id = str(uuid.uuid4())  # Generate unique flight ID

        # Use campaign's callsign list if useSquadronCallsigns is set
        use_squadron_callsign = slot_to_claim.get("useSquadronCallsigns", False)
        if use_squadron_callsign:
            callsign_prefix = get_callsign(squadron, campaign_id)
        else:
            callsign_prefix = slot_to_claim.get("label") or get_callsign(squadron, campaign_id)
        full_callsign = f"{callsign_prefix} 11"  # Standard DCS format: prefix + 11 for lead

        new_flight = {
            "flight_id": flight_id,  # Correct field name for Flight.from_dict()
            "mission_id": mission_id,  # Required by Flight.from_dict()
            "squadron": squadron,  # Selected squadron
            "callsign": callsign_prefix,  # Use callsign prefix for flight
            "flight_number": 1,  # Set to 1 for first flight of this callsign
            "departure_base": departure_base,
            "recovery_base": recovery_base or departure_base,
            "operations_area": operations_area,
            "mission_type": slot_to_claim.get("role", ""),  # Use role as mission type
            "remarks": remarks,
            "aircraft_ids": [aircraft_id] if aircraft_id else [],
            "transponder_codes": [],  # Will be assigned later
            "tacan_channel": "",  # Will be assigned later
            "intraflight_freq": "",  # Will be assigned later
            "pilots": [{
                "user_id": session.get("user_id"),
                "username": current_user,
                "nickname": session.get("display_name", current_user),
                "position": "1",  # Flight lead position
                "joined_at": datetime.now().isoformat(),  # Add joined_at timestamp
                "callsign": full_callsign,  # Full callsign for pilot (e.g., VIKING 11)
                "transponder": None,  # Will be assigned later
                "aircraft": aircraft_id,  # Selected aircraft
                "aircraft_id": aircraft_id  # For template compatibility
            }],
            "status": "active",
            "side": "blue",  # Required by Flight.from_dict(), default to blue
            "created_at": datetime.now().isoformat(),
            "claimed_from_slot": slot_idx  # Track which slot this came from
        }
        
        # Initialize flights dict if it doesn't exist
        if "flights" not in mission:
            mission["flights"] = {}
        
        # Add the new flight to the mission using the flight ID as key
        mission["flights"][flight_id] = new_flight
        
        # Remove the claimed slot from curated_slots
        mission["curated_slots"].pop(slot_idx)
        
        # Save the updated mission
        save_mission(mission)
        
        flash(f"Successfully claimed slot '{slot_to_claim.get('label', 'Unknown')}' and created flight with callsign '{new_flight['callsign']}'!", "success")
        logger.info(f"[SIGNUP] User {current_user} successfully claimed slot {slot_idx} in mission {mission_id}, created flight {flight_id}")
        
    except Exception as e:
        logger.error(f"[SIGNUP] Error claiming slot {slot_idx} in mission {mission_id}: {str(e)}")
        flash("An error occurred while claiming the slot. Please try again.", "danger")
    
    return redirect(url_for("signup.signup_mission", mission_id=mission_id))