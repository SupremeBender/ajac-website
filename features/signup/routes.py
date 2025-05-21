from flask import render_template, redirect, url_for, request, current_app, flash, session, jsonify
from . import signup_bp
import logging
import requests
import re
from datetime import datetime
from utils.storage import load_mission, load_campaign
from features.missions.routes import storage_list_missions
from utils.auth import login_required
from models.flight import (create_flight, get_flight, get_mission_flights_data,
                          join_flight, leave_flight, delete_flight)
from utils.resources import (get_squadrons, get_bases, get_operations_areas, 
                           get_aircraft_at_base)
import os
import json

logger = logging.getLogger(__name__)

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
        resp = requests.get(f"http://localhost:8000/roles/{user_id}", timeout=2)
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
        resp = requests.get(f"http://localhost:8000/roles/{user_id}", timeout=2)
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
    if campaign_id:
        campaign = load_campaign(campaign_id)
        if campaign:
            persistent_ac_location = campaign.get("persistent_ac_location", False)
    
    # Get all flights for this mission
    flights = get_mission_flights_data(mission_id)
    
    # Get resources for flight creation
    squadrons = get_squadrons()
    bases = get_bases()
    operations_areas = get_operations_areas()

    # Load mission types from config/mission_types.json (fix path)
    mission_types_path = os.path.join(current_app.root_path, "config", "mission_types.json")
    logger.info(f"[MISSION_TYPES] Using mission_types_path: {mission_types_path}")
    if not os.path.isfile(mission_types_path):
        logger.error(f"[MISSION_TYPES] File does not exist: {mission_types_path}")
        flash(f"mission_types.json not found at {mission_types_path}", "danger")
        mission_types = {}
    else:
        try:
            with open(mission_types_path) as f:
                mission_types = json.load(f)  # Pass the full dict, not just keys
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
            if pilot["user_id"] == user_id:
                user_flight = flight
                user_position = pilot["position"]
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
        persistent_ac_location=persistent_ac_location
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
        resp = requests.get(f"http://localhost:8000/roles/{user_id}", timeout=2)
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
        resp = requests.get(f"http://localhost:8000/roles/{user_id}", timeout=2)
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
    username = display_name
    
    # Get form data
    squadron = request.form.get("squadron")
    departure_base = request.form.get("departure_base")
    recovery_base = request.form.get("recovery_base")
    operations_area = request.form.get("operations_area")
    mission_type = request.form.get("mission_type")
    remarks = request.form.get("remarks")
    aircraft_id = request.form.get("aircraft_id")
    logger.debug(f"[CREATE_NEW_FLIGHT] Received form data: squadron={squadron}, departure_base={departure_base}, recovery_base={recovery_base}, operations_area={operations_area}, mission_type={mission_type}, remarks={remarks}, aircraft_id={aircraft_id}")
    
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
        "aircraft_id": aircraft_id
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
        resp = requests.get(f"http://localhost:8000/roles/{user_id}", timeout=2)
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
    
    if not base_id:
        return jsonify({"error": "Base ID required"}), 400
    
    # Get aircraft at the base
    aircraft = get_aircraft_at_base(base_id)
    
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
    from utils.resources import get_bases, get_aircraft_at_base
    bases = []
    all_bases = get_bases()
    if persistent:
        # Only show bases where this squadron has aircraft
        for base_id, base in all_bases.items():
            aircraft = get_aircraft_at_base(base_id)
            if any(ac.get("squadron") == squadron for ac in aircraft.values()):
                bases.append(base_id)
    else:
        # Show all bases
        bases = list(all_bases.keys())
    return jsonify({"bases": bases})

@signup_bp.route("/squadron-aircraft", methods=["POST"])
@login_required
def squadron_aircraft_endpoint():
    """Return a list of aircraft for a given squadron and base (AJAX)"""
    squadron = request.form.get("squadron")
    base = request.form.get("base")
    persistent = request.form.get("persistent", "1") == "1"
    mission_id = request.form.get("mission_id")
    from utils.resources import get_resources
    resources = get_resources()
    all_aircraft = resources.get("aircraft", {})

    # Get all flights for this mission to check which aircraft are in use
    in_use_aircraft = set()
    if mission_id:
        from models.flight import get_mission_flights_data
        flights = get_mission_flights_data(mission_id)
        for flight in flights:
            for pilot in flight.pilots:
                if pilot.get("aircraft"):
                    in_use_aircraft.add(str(pilot["aircraft"]))

    if persistent:
        # Show all squadron aircraft NOT in use, regardless of base
        aircraft = [tail for tail, meta in all_aircraft.items()
                    if meta.get("squadron") == squadron and str(tail) not in in_use_aircraft]
    else:
        # Show all squadron aircraft (regardless of base), but not in use
        aircraft = [tail for tail, meta in all_aircraft.items()
                    if meta.get("squadron") == squadron and str(tail) not in in_use_aircraft]
    # Optionally, include base info for frontend display
    aircraft_info = []
    for tail in aircraft:
        meta = all_aircraft.get(str(tail), {})
        aircraft_info.append({
            "tail": str(tail),
            "type": meta.get("type", ""),
            "location": meta.get("location", "")
        })
    return jsonify({"aircraft": aircraft_info})