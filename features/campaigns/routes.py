from flask import render_template, redirect, url_for, request, flash, current_app
from . import campaigns_bp
from utils.storage import save_campaign, list_campaigns, load_campaign
from datetime import datetime
import logging
from utils.auth import login_required
import os, json

logger = logging.getLogger(__name__)

def get_config_dir():
    """Get the global data directory path"""
    config_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../instance/data'))
    import logging
    logging.getLogger().setLevel(logging.DEBUG)
    logging.debug(f"[DEBUG] get_config_dir: {config_dir}")
    return config_dir

def get_theatres():
    """Get theatres with caching for performance"""
    from utils.cache import get_cached_json
    theatres_dir = os.path.join(get_config_dir(), 'theatres')
    import logging
    logging.debug(f"[DEBUG] get_theatres: listing files in {theatres_dir}")
    try:
        files = os.listdir(theatres_dir)
        logging.debug(f"[DEBUG] Files in theatres_dir: {files}")
    except Exception as e:
        logging.debug(f"[DEBUG] Error listing theatres_dir: {e}")
        return []
    theatres = []
    for fname in files:
        if fname.endswith('.json'):
            path = os.path.join(theatres_dir, fname)
            try:
                # Use cached loading for theatre files
                data = get_cached_json(path)
                logging.debug(f"[DEBUG] Loaded {fname}: {data}")
                theatres.append({
                    'name': data.get('name', fname.replace('.json', '').capitalize()),
                    'filename': fname
                })
            except Exception as e:
                logging.debug(f"[DEBUG] Error loading {path}: {e}")
                continue
    logging.debug(f"[DEBUG] Theatres found: {theatres}")
    return theatres

def get_bases_for_theatre(theatre_filename):
    """Get bases for theatre with caching for performance"""
    from utils.cache import get_cached_json
    theatres_dir = os.path.join(get_config_dir(), 'theatres')
    path = os.path.join(theatres_dir, theatre_filename)
    try:
        # Use cached loading for theatre files
        data = get_cached_json(path)
        # Debug: print loaded data
        logger.debug(f"[DEBUG] Loaded theatre file: {data}")
        return data.get('bases', [])
    except Exception as e:
        logger.debug(f"[DEBUG] Error loading bases for {theatre_filename}: {e}")
        return []

def get_squadrons():
    """Get squadrons with caching for performance - using squadron templates"""
    from utils.squadron_manager import squadron_manager
    try:
        # Get all available squadron templates
        templates = squadron_manager.get_squadron_templates()
        # Convert to the format expected by the frontend
        squadrons = {}
        for squadron_id, template in templates.items():
            squadrons[squadron_id] = {
                'name': template.get('name', f'Squadron {squadron_id}'),
                'aircraft_type': template.get('aircraft_type', 'UNKNOWN'),
                'callsigns': template.get('callsigns', [squadron_id])
            }
        return squadrons
    except Exception as e:
        logger.error(f"Failed to load squadron templates: {e}")
        return {}

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
    """Create a new campaign"""
    theatres = get_theatres()
    squadrons = get_squadrons()
    
    def getval(key, default=None, multi=False):
        if request.method == 'POST':
            if multi:
                return request.form.getlist(key)
            return request.form.get(key, default)
        else:
            if multi:
                return request.args.getlist(key)
            return request.args.get(key, default)
    
    selected_theatre = getval('theatre')
    
    # Get bases for selected theatre (avoid logging unicode characters)
    if selected_theatre:
        logger.debug(f"Selected theatre: {selected_theatre}")
        bases = get_bases_for_theatre(selected_theatre)
        logger.debug(f"Found {len(bases)} bases for theatre")
    else:
        bases = []
    if request.method == "POST":
        name = getval("name")
        shorthand = getval("shorthand")
        type_ = getval("type")
        status = getval("status", "active")
        persistent_ac_location = getval("persistent_ac_location") == "on"
        theatre = getval('theatre')
        squadron_ids = getval('squadrons', multi=True)
        squadron_bases = {sq: getval(f'base_{sq}') for sq in squadron_ids}
        
        # Build campaign squadrons structure using template system (NEW FORMAT)
        campaign_squadrons = {}
        from utils.squadron_manager import squadron_manager
        for sq_id in squadron_ids:
            # Get base squadron template
            base_template = squadron_manager.get_squadron_templates().get(sq_id, {})
            if not base_template:
                logger.warning(f"Squadron template {sq_id} not found, skipping")
                continue
            base_id = squadron_bases.get(sq_id)
            # Build new squadron entry with all template info and assign aircraft locations
            new_entry = {
                'name': base_template.get('name', sq_id),
                'aircraft_type': base_template.get('aircraft_type', ''),
                'callsigns': base_template.get('callsigns', []),
                'aircraft': []
            }
            tail_numbers = base_template.get('tail_numbers', [])
            for t in tail_numbers:
                tail = t['tail'] if isinstance(t, dict) and 'tail' in t else str(t)
                new_entry['aircraft'].append({
                    'tail': tail,
                    'location': base_id,
                    'state': 100
                })
            campaign_squadrons[sq_id] = new_entry
        campaign_data = {
            "name": name,
            "shorthand": shorthand,
            "type": type_,
            "status": status,
            "persistent_ac_location": persistent_ac_location,
            "theatre": theatre,
            "squadrons": campaign_squadrons
        }
        
        # Save campaign first to get the campaign ID
        campaign_id = save_campaign(campaign_data)
        
        # Generate and save aircraft state for the new campaign
        try:
            from utils.aircraft_state import generate_campaign_aircraft_state, save_campaign_aircraft_state
            aircraft_state = generate_campaign_aircraft_state(campaign_data)
            if aircraft_state:
                save_campaign_aircraft_state(campaign_id, aircraft_state)
                logger.info(f"Generated aircraft state for new campaign {campaign_id} ({len(aircraft_state)} aircraft)")
            else:
                logger.warning(f"No aircraft state generated for campaign {campaign_id}")
        except Exception as e:
            logger.error(f"Failed to generate aircraft state for campaign {campaign_id}: {e}")
            flash("Campaign created but aircraft state generation failed. Check logs.", "warning")
        
        flash(f"Campaign '{name}' created successfully!")
        return redirect(url_for("campaigns.list_campaigns_route"))
    return render_template(
        "create_campaign.html",
        theatres=theatres,
        squadrons=squadrons,
        bases=bases,
        selected_theatre=selected_theatre,
        current_year=datetime.now().year
    )

@campaigns_bp.route("/edit/<campaign_id>", methods=["GET", "POST"])
@login_required
def edit_campaign(campaign_id):
    theatres = get_theatres()
    squadrons = get_squadrons()
    campaign = load_campaign(campaign_id)
    if not campaign:
        flash("Campaign not found.", "danger")
        return redirect(url_for("campaigns.list_campaigns_route"))
    selected_theatre = campaign.get("theatre")
    bases = get_bases_for_theatre(selected_theatre) if selected_theatre else []
    if request.method == "POST":
        def getval(key, default=None, multi=False):
            if multi:
                return request.form.getlist(key)
            return request.form.get(key, default)
        name = getval("name", campaign.get("name"))
        shorthand = getval("shorthand", campaign.get("shorthand"))
        type_ = getval("type", campaign.get("type"))
        status = getval("status", campaign.get("status", "active"))
        persistent_ac_location = getval("persistent_ac_location") == "on"
        theatre = getval('theatre', campaign.get('theatre'))
        squadron_ids = getval('squadrons', multi=True)
        squadron_bases = {sq: getval(f'base_{sq}') for sq in squadron_ids}
        
        # Build campaign squadrons structure using new template system
        campaign_squadrons = {}
        
        from utils.squadron_manager import squadron_manager
        
        for sq_id in squadron_ids:
            # Get base squadron template
            base_template = squadron_manager.get_squadron_templates().get(sq_id, {})
            if not base_template:
                logger.warning(f"Squadron template {sq_id} not found, skipping")
                continue
            
            # Use template system
            base_id = squadron_bases.get(sq_id)
            
            # Add minimal squadron reference to campaign (templates handle the rest)
            campaign_squadrons[sq_id] = {
                'id': sq_id,
                'base': base_id
            }
        
        campaign_data = {
            "id": campaign_id,
            "name": name,
            "shorthand": shorthand,
            "type": type_,
            "status": status,
            "persistent_ac_location": persistent_ac_location,
            "theatre": theatre,
            "squadrons": campaign_squadrons
        }
        
        save_campaign(campaign_data)
        flash(f"Campaign '{name}' updated successfully!", "success")
        return redirect(url_for("campaigns.list_campaigns_route"))
    # For GET, pre-populate form fields using campaign data
    return render_template(
        "create_campaign.html",
        theatres=theatres,
        squadrons=squadrons,
        bases=bases,
        selected_theatre=selected_theatre,
        current_year=datetime.now().year,
        edit_mode=True,
        campaign=campaign
    )

@campaigns_bp.route("/add_squadron", methods=["POST"])
@login_required
def add_squadron_to_campaign():
    """Add a squadron to a campaign, copying all info from the template and assigning aircraft locations."""
    import os
    from flask import request, jsonify
    from utils.squadron_manager import squadron_manager
    from utils.storage import save_json, load_json

    campaign_id = request.form.get("campaign_id")
    squadron_id = request.form.get("squadron_id")
    base = request.form.get("base")
    if not (campaign_id and squadron_id and base):
        return jsonify({"error": "Missing required fields"}), 400

    # Load squadron template
    template = squadron_manager.get_squadron_templates().get(squadron_id)
    if not template:
        return jsonify({"error": "Squadron template not found"}), 404

    # Prepare campaign squadrons.json path
    campaign_dir = os.path.join(os.path.dirname(__file__), '../../instance/campaigns', campaign_id)
    squadrons_path = os.path.join(campaign_dir, 'squadrons.json')
    if os.path.exists(squadrons_path):
        campaign_squadrons = load_json(squadrons_path).get('squadrons', {})
    else:
        campaign_squadrons = {}

    # Build new squadron entry with all template info and assign aircraft locations
    new_entry = {
        'name': template.get('name', squadron_id),
        'aircraft_type': template.get('aircraft_type', ''),
        'callsigns': template.get('callsigns', []),
        'aircraft': []
    }
    tail_numbers = template.get('tail_numbers', [])
    for t in tail_numbers:
        tail = t['tail'] if isinstance(t, dict) and 'tail' in t else str(t)
        new_entry['aircraft'].append({
            'tail': tail,
            'location': base,
            'state': 100
        })

    # Add or update the squadron in the dict
    campaign_squadrons[squadron_id] = new_entry
    save_json(squadrons_path, {'squadrons': campaign_squadrons})
    return jsonify({"success": True, "squadron": new_entry})
