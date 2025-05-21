from flask import render_template, redirect, url_for, request, current_app, flash
from . import missions_bp
import logging
from datetime import datetime
from utils.storage import generate_mission_id, save_mission, list_missions as storage_list_missions, list_campaigns, load_mission
from utils.auth import login_required

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
    if request.method == "POST":
        campaign_id = request.form.get("campaign_id")
        short_description = request.form.get("short_description")
        description = request.form.get("description")
        # Get campaign shorthand and type
        campaign = next((c for c in campaigns if c["id"] == campaign_id), None)
        operation_code = campaign["shorthand"] if campaign else ""
        mission_type = campaign["type"] if campaign else "EX"
        # Dates/times
        start_date_real = request.form.get("start_date_real")
        start_time_real = request.form.get("start_time_real")
        start_date_ingame = request.form.get("start_date_ingame")
        start_time_ingame = request.form.get("start_time_ingame")
        # Combine date and time fields
        time_real = f"{start_date_real}T{start_time_real}" if start_date_real and start_time_real else None
        time_ingame = f"{start_date_ingame}T{start_time_ingame}" if start_date_ingame and start_time_ingame else None
        # Easy mode
        flight_plan_easy_mode = bool(request.form.get("flight_plan_easy_mode"))
        # Generate mission ID (auto-increment sequence)
        mission_id = generate_mission_id(operation_code, mission_type)
        # Stylized name for display
        mission_name = f"{operation_code} | {mission_type}{mission_id[-2:]}"
        mission_data = {
            "id": mission_id,  # always the simplified ID (e.g. PP15EX01)
            "name": mission_name,  # always the stylized name (e.g. PP15 | EX01)
            "campaign_id": campaign_id,
            "short_description": short_description,
            "description": description,
            "time_real": time_real,
            "time_ingame": time_ingame,
            "status": "planned",
            "flight_plan_easy_mode": flight_plan_easy_mode
        }
        save_mission(mission_data)
        flash(f"Mission created successfully! ID: {mission_id}")
        return redirect(url_for("missions.list_missions"))
    else:
        campaign_id = request.args.get("campaign_id", "")
        campaign = next((c for c in campaigns if c["id"] == campaign_id), None)
        operation_code = campaign["shorthand"] if campaign else ""
        mission_type = campaign["type"] if campaign else "EX"
        if operation_code:
            # Always generate the next available mission ID for preview
            mission_id_preview = generate_mission_id(operation_code, mission_type)
    return render_template(
        "create_mission.html",
        current_year=datetime.now().year,
        mission_id_preview=mission_id_preview,
        campaigns=campaigns
    )

@missions_bp.route("/<mission_id>")
@login_required
def view_mission(mission_id):
    """View a specific mission"""
    mission = load_mission(mission_id)
    if not mission:
        flash("Mission not found.", "danger")
        return redirect(url_for("missions.list_missions"))
    return render_template(
        "view.html",
        mission=mission,
        current_year=datetime.now().year
    )

@missions_bp.route("/edit/<mission_id>", methods=["GET", "POST"])
@login_required
def edit_mission(mission_id):
    from utils.storage import load_mission, save_mission, list_campaigns
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
        # Update mission fields
        mission["campaign_id"] = campaign_id
        mission["short_description"] = short_description
        mission["description"] = description
        mission["name"] = name
        mission["time_real"] = time_real
        mission["time_ingame"] = time_ingame
        mission["flight_plan_easy_mode"] = flight_plan_easy_mode
        save_mission(mission)
        flash(f"Mission '{mission['name']}' updated successfully!", "success")
        return redirect(url_for("missions.list_missions"))
    # For GET, parse date/time fields for form population
    start_date_real, start_time_real = (mission.get("time_real", "T").split("T") + [""])[:2]
    start_date_ingame, start_time_ingame = (mission.get("time_ingame", "T").split("T") + [""])[:2]
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
        start_time_ingame=start_time_ingame
    )