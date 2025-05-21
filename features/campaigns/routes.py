from flask import render_template, redirect, url_for, request, flash
from . import campaigns_bp
from utils.storage import save_campaign, list_campaigns
from datetime import datetime
import logging
from utils.auth import login_required

logger = logging.getLogger(__name__)

@campaigns_bp.route("/", methods=["GET"])
@login_required
def list_campaigns_route():
    campaigns = list_campaigns()
    logger.debug(f"accessed campaigns root")
    return render_template(
        "list_campaigns.html",
        campaigns=campaigns,
        current_year=datetime.now().year
    )

@campaigns_bp.route("/create", methods=["GET", "POST"])
@login_required
def create_campaign():
    if request.method == "POST":
        name = request.form.get("name")
        shorthand = request.form.get("shorthand")
        type_ = request.form.get("type")
        status = request.form.get("status", "active")
        persistent_ac_location = request.form.get("persistent_ac_location") == "on"
        campaign_data = {
            "name": name,
            "shorthand": shorthand,
            "type": type_,
            "status": status,
            "persistent_ac_location": persistent_ac_location  # True/False
        }
        save_campaign(campaign_data)
        flash(f"Campaign '{name}' created successfully!")
        return redirect(url_for("campaigns.list_campaigns_route"))
    return render_template("create_campaign.html", current_year=datetime.now().year)
