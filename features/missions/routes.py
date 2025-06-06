from flask import render_template, redirect, url_for, request, current_app, flash, jsonify, session
from . import missions_bp
import logging
from datetime import datetime
from utils.storage import generate_mission_id, save_mission, list_missions as storage_list_missions, list_campaigns, load_mission
from utils.auth import login_required
import json
import os
import uuid

logger = logging.getLogger(__name__)

@missions_bp.route("/", methods=["GET"])
@login_required
def list_missions():
    """Show list of available missions"""
    logger.debug(f"accessed missions root")
    missions = storage_list_missions()
    return render_template(
        "list_missions.html",
        missions=missions,
        current_year=datetime.now().year
    )

@missions_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_mission():
    """Create a new mission"""
    campaigns = list_campaigns()
    mission_id_preview = None
    # Determine campaign (from POST or GET)
    if request.method == "POST":
        campaign_id = request.form.get("campaign_id")
    else:
        campaign_id = request.args.get("campaign_id", "")
    # Load full campaign data (not just summary)
    from utils.storage import load_campaign, load_reference_data
    campaign = load_campaign(campaign_id) if campaign_id else None
    
    # Load mission types
    mission_types = load_reference_data("mission_types")
    
    # Use enhanced squadron system with template integration
    from utils.squadron_manager import squadron_manager
    if campaign and "squadrons" in campaign and campaign["squadrons"]:
        # Always pass the squadrons dict directly (new format)
        squadrons = squadron_manager.get_campaign_squadrons(campaign_id, campaign["squadrons"])
        logger.info(f"[MISSIONS] Loaded {len(squadrons)} campaign squadrons for campaign {campaign_id}.")
    else:
        squadrons = {}
        logger.info(f"[MISSIONS] No squadrons for campaign {campaign_id} or campaign not selected.")
    if request.method == "POST":
        short_description = request.form.get("short_description")
        description = request.form.get("description")
        operation_code = campaign["shorthand"] if campaign else ""
        mission_type = campaign["type"] if campaign else "EX"
        start_date_real = request.form.get("start_date_real")
        start_time_real = request.form.get("start_time_real")
        start_date_ingame = request.form.get("start_date_ingame")
        start_time_ingame = request.form.get("start_time_ingame")
        time_real = f"{start_date_real}T{start_time_real}" if start_date_real and start_time_real else None
        time_ingame = f"{start_date_ingame}T{start_time_ingame}" if start_date_ingame and start_time_ingame else None
        flight_plan_easy_mode = bool(request.form.get("flight_plan_easy_mode"))
        # Parse curated slots and open flights
        curated_slots_raw = request.form.get("curated_slots", "[]")
        try:
            curated_slots = json.loads(curated_slots_raw)
        except Exception:
            curated_slots = []
        allow_open_flights = bool(request.form.get("allow_open_flights"))
        mission_id = generate_mission_id(operation_code, mission_type)
        mission_name = f"{operation_code} | {mission_type}{mission_id[-2:]}"
        mission_data = {
            "id": mission_id,
            "name": mission_name,
            "campaign_id": campaign_id,
            "short_description": short_description,
            "description": description,
            "time_real": time_real,
            "time_ingame": time_ingame,
            "status": "planned",
            "flight_plan_easy_mode": flight_plan_easy_mode,
            "curated_slots": curated_slots,
            "allow_open_flights": allow_open_flights
        }
        save_mission(mission_data)
        flash(f"Mission created successfully! ID: {mission_id}")
        return redirect(url_for("missions.list_missions"))
    else:
        operation_code = campaign["shorthand"] if campaign else ""
        mission_type = campaign["type"] if campaign else "EX"
        if operation_code:
            mission_id_preview = generate_mission_id(operation_code, mission_type)
    return render_template(
        "create_mission.html",
        current_year=datetime.now().year,
        mission_id_preview=mission_id_preview,
        campaigns=campaigns,
        squadrons=squadrons,
        mission_types=mission_types
    )

@missions_bp.route("/<mission_id>")
@login_required
def view_mission(mission_id):
    """View a specific mission"""
    logger.info(f"[MISSIONS] Viewing mission {mission_id}")
    mission = load_mission(mission_id)
    if not mission:
        flash("Mission not found.", "danger")
        return redirect(url_for("missions.list_missions"))
    
    # Add user context for template
    current_user = session.get("username", "Unknown User")
    is_authenticated = bool(session.get("user_id"))
    
    logger.info(f"[MISSIONS] Mission {mission_id} loaded with {len(mission.get('curated_slots', []))} curated slots and {len(mission.get('flights', {}))} flights")
    
    return render_template(
        "view.html",
        mission=mission,
        current_year=datetime.now().year,
        current_user=current_user,
        is_authenticated=is_authenticated
    )

@missions_bp.route("/edit/<mission_id>", methods=["GET", "POST"])
@login_required
def edit_mission(mission_id):
    from utils.storage import load_mission, save_mission, list_campaigns, load_reference_data
    mission = load_mission(mission_id)
    if not mission:
        flash("Mission not found.", "danger")
        return redirect(url_for("missions.list_missions"))
    campaigns = list_campaigns()
    if request.method == "POST":
        campaign_id = request.form.get("campaign_id")
        short_description = request.form.get("short_description")
        description = request.form.get("description")
        name = request.form.get("name")
        start_date_real = request.form.get("start_date_real")
        start_time_real = request.form.get("start_time_real")
        start_date_ingame = request.form.get("start_date_ingame")
        start_time_ingame = request.form.get("start_time_ingame")
        time_real = f"{start_date_real}T{start_time_real}" if start_date_real and start_time_real else None
        time_ingame = f"{start_date_ingame}T{start_time_ingame}" if start_date_ingame and start_time_ingame else None
        # Easy mode
        flight_plan_easy_mode = bool(request.form.get("flight_plan_easy_mode"))
        # Parse curated slots and open flights
        curated_slots_raw = request.form.get("curated_slots", "[]")
        try:
            curated_slots = json.loads(curated_slots_raw)
        except Exception:
            curated_slots = []
        allow_open_flights = bool(request.form.get("allow_open_flights"))
        # Update mission fields
        mission["campaign_id"] = campaign_id
        mission["short_description"] = short_description
        mission["description"] = description
        mission["name"] = name
        mission["time_real"] = time_real
        mission["time_ingame"] = time_ingame
        mission["flight_plan_easy_mode"] = flight_plan_easy_mode
        mission["curated_slots"] = curated_slots
        mission["allow_open_flights"] = allow_open_flights

        # --- REMOVE: AUTO-GENERATE FLIGHTS FROM CURATED SLOTS ---
        # Curated slots remain as templates until claimed by a flight lead.
        # mission['flights'] is not modified here.

        save_mission(mission)
        flash(f"Mission '{mission['name']}' updated successfully!", "success")
        return redirect(url_for("missions.list_missions"))
    # For GET, parse date/time fields for form population
    # Defensive: handle None for time_real/time_ingame
    time_real = mission.get("time_real")
    if time_real:
        start_date_real, start_time_real = (time_real.split("T") + [""])[:2]
    else:
        start_date_real, start_time_real = "", ""
    time_ingame = mission.get("time_ingame")
    if time_ingame:
        start_date_ingame, start_time_ingame = (time_ingame.split("T") + [""])[:2]
    else:
        start_date_ingame, start_time_ingame = "", ""

    # --- SQUADRONS: Always provide a serializable value with enhanced template system ---
    from utils.storage import load_campaign
    from utils.squadron_manager import squadron_manager
    campaign_id = mission.get("campaign_id")
    campaign = load_campaign(campaign_id) if campaign_id else None
    if campaign and "squadrons" in campaign and campaign["squadrons"]:
        squadrons = squadron_manager.get_campaign_squadrons(campaign_id, campaign["squadrons"])
        logger.info(f"[MISSIONS] Loaded {len(squadrons)} campaign squadrons for campaign {campaign_id} (edit mode).")
    else:
        squadrons = {}
        logger.info(f"[MISSIONS] No squadrons for campaign {campaign_id} or campaign not found (edit mode).")

    # Load mission types for the template
    from utils.storage import load_reference_data
    mission_types = load_reference_data("mission_types")

    return render_template(
        "create_mission.html",
        edit_mode=True,
        mission=mission,
        campaigns=campaigns,
        mission_id_preview=mission["id"],
        current_year=datetime.now().year,
        start_date_real=start_date_real,
        start_time_real=start_time_real,
        start_date_ingame=start_date_ingame,
        start_time_ingame=start_time_ingame,
        squadrons=squadrons,
        mission_types=mission_types
    )

@missions_bp.route("/get_squadrons_for_campaign", methods=["GET"])
@login_required
def get_squadrons_for_campaign():
    """AJAX endpoint: Return squadrons for a given campaign ID as JSON with template enhancement."""
    campaign_id = request.args.get("campaign_id")
    if not campaign_id:
        return jsonify({"error": "No campaign_id provided"}), 400
    from utils.storage import load_campaign
    from utils.squadron_manager import squadron_manager
    campaign = load_campaign(campaign_id)
    
    if campaign and "squadrons" in campaign:
        enhanced_squadrons = squadron_manager.get_campaign_squadrons(campaign_id, campaign["squadrons"])
        return jsonify(enhanced_squadrons)
    else:
        return jsonify({})

@missions_bp.route("/claim_curated_slot/<mission_id>/<int:slot_index>", methods=["POST"])
@login_required
def claim_curated_slot(mission_id, slot_index):
    """Claim a curated slot and convert it into a real flight"""
    current_user = session.get("username")
    if not current_user:
        flash("You must be logged in to claim a slot.", "danger")
        return redirect(url_for("auth.login"))
    
    logger.info(f"[MISSIONS] User {current_user} attempting to claim slot {slot_index} in mission {mission_id}")
    
    # Load the mission
    mission = load_mission(mission_id)
    if not mission:
        flash("Mission not found.", "danger")
        return redirect(url_for("missions.list_missions"))
    
    # Validate slot index
    curated_slots = mission.get("curated_slots", [])
    if slot_index < 0 or slot_index >= len(curated_slots):
        flash("Invalid slot index.", "danger")
        logger.warning(f"[MISSIONS] Invalid slot index {slot_index} for mission {mission_id}")
        return redirect(url_for("missions.view_mission", mission_id=mission_id))
    
    # Get the curated slot to claim
    slot_to_claim = curated_slots[slot_index]
    
    # Get form data for additional flight details
    flight_name = request.form.get("flight_name", slot_to_claim.get("label", "Unknown Flight"))
    description = request.form.get("description", "")
    
    try:
        # Create new flight from curated slot
        new_flight = {
            "id": str(uuid.uuid4()),  # Generate unique flight ID
            "name": flight_name,
            "callsign": slot_to_claim.get("label", ""),  # Use label as callsign
            "role": slot_to_claim.get("role", ""),
            "squadrons": slot_to_claim.get("squadrons", []),
            "description": description,
            "original_slot_description": slot_to_claim.get("description", ""),
            "lead": current_user,  # User who claimed the slot becomes flight lead
            "members": [current_user],  # Flight lead is automatically a member
            "max_pilots": slot_to_claim.get("seats", 1),  # Use seats as max_pilots
            "status": "active",
            "created_at": datetime.now().isoformat(),
            "claimed_from_slot": slot_index  # Track which slot this came from
        }
        
        # Initialize flights dict if it doesn't exist
        if "flights" not in mission:
            mission["flights"] = {}
        
        # Add the new flight to the mission using the flight ID as key
        mission["flights"][new_flight["id"]] = new_flight
        
        # Remove the claimed slot from curated_slots
        mission["curated_slots"].pop(slot_index)
        
        # Save the updated mission
        save_mission(mission)
        
        flash(f"Successfully claimed slot '{slot_to_claim.get('label', 'Unknown')}' and created flight '{flight_name}'!", "success")
        logger.info(f"[MISSIONS] User {current_user} successfully claimed slot {slot_index} in mission {mission_id}, created flight {new_flight['id']}")
        
    except Exception as e:
        logger.error(f"[MISSIONS] Error claiming slot {slot_index} in mission {mission_id}: {str(e)}")
        flash("An error occurred while claiming the slot. Please try again.", "danger")
    
    return redirect(url_for("missions.view_mission", mission_id=mission_id))