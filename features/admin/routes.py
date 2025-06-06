from flask import Blueprint, render_template, request, redirect, url_for, flash
import json
import os
from werkzeug.utils import secure_filename
from utils.auth import admin_required

admin_bp = Blueprint('admin', __name__, template_folder='templates')

SQUADRONS_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'config', 'squadrons.json')

@admin_bp.route('/admin/create_squadron', methods=['GET', 'POST'])
def create_squadron():
    if request.method == 'POST':
        # Get form data
        squadron_id = request.form.get('squadron_id').strip()
        name = request.form.get('name').strip()
        aircraft_type = request.form.get('aircraft_type').strip()
        callsigns = [c.strip() for c in request.form.get('callsigns', '').split(',') if c.strip()]
        tail_numbers = []
        for tail in request.form.getlist('tail[]'):
            if tail.strip():
                tail_numbers.append({'tail': tail.strip()})
        # Load, update, and save squadrons.json
        try:
            with open(SQUADRONS_PATH, 'r', encoding='utf-8') as f:
                squadrons = json.load(f)
        except Exception:
            squadrons = {}
        if squadron_id in squadrons:
            flash('Squadron ID already exists!', 'danger')
            return render_template('create_squadron.html')
        squadrons[squadron_id] = {
            'name': name,
            'aircraft_type': aircraft_type,
            'tail_numbers': tail_numbers,
            'callsigns': callsigns
        }
        with open(SQUADRONS_PATH, 'w', encoding='utf-8') as f:
            json.dump(squadrons, f, indent=2)
        flash('Squadron created successfully!', 'success')
        return redirect(url_for('admin.create_squadron'))
    return render_template('create_squadron.html')

@admin_bp.route('/squadrons')
@admin_required
def list_squadrons():
    """
    List all squadrons with options to edit or delete - enhanced with template support.
    """
    import json
    from flask import current_app, render_template, flash
    from utils.squadron_manager import squadron_manager
    
    try:
        # Get squadrons from enhanced template system
        squadrons = squadron_manager.get_squadron_templates()
        # Convert to format expected by the template (backward compatibility)
        legacy_format = {}
        for squadron_id, template in squadrons.items():
            legacy_format[squadron_id] = {
                'name': template.get('name', f'Squadron {squadron_id}'),
                'aircraft_type': template.get('aircraft_type', 'UNKNOWN'),
                'callsigns': template.get('callsigns', [squadron_id]),
                'tail_numbers': template.get('aircraft_inventory', {}).get('tail_numbers', [])
            }
        squadrons = legacy_format
    except Exception as e:
        # Fallback to legacy loading
        from utils.cache import get_cached_json
        squadrons_path = current_app.config.get('SQUADRONS_PATH', '/var/www/beta.ajac.no/instance/data/squadron_templates/squadron_templates.json')
        try:
            squadrons = get_cached_json(squadrons_path)
        except Exception as fallback_e:
            squadrons = {}
            flash(f"Error loading squadrons from both template system and legacy: {e}, {fallback_e}", "danger")
    
    return render_template('list_squadrons.html', squadrons=squadrons)

@admin_bp.route('/squadron/edit/<squadron_id>', methods=['GET', 'POST'])
@admin_required
def edit_squadron(squadron_id):
    """
    Edit an existing squadron. Reuses the create_squadron form.
    """
    import json
    from flask import current_app, render_template, request, redirect, url_for, flash
    squadrons_path = current_app.config.get('SQUADRONS_PATH', '/var/www/beta.ajac.no/config/squadrons.json')
    try:
        with open(squadrons_path, 'r') as f:
            squadrons = json.load(f)
    except Exception as e:
        squadrons = {}
        flash(f"Error loading squadrons: {e}", "danger")
        return redirect(url_for('admin.list_squadrons'))
    squadron = squadrons.get(squadron_id)
    if not squadron:
        flash("Squadron not found.", "danger")
        return redirect(url_for('admin.list_squadrons'))
    if request.method == 'POST':
        # Validate and update squadron
        name = request.form.get('name', '').strip()
        aircraft_type = request.form.get('aircraft_type', '').strip()
        tail_numbers = request.form.get('tail_numbers', '').strip().split(',')
        callsigns = request.form.get('callsigns', '').strip().split(',')
        if not name or not aircraft_type:
            flash("Name and aircraft type are required.", "danger")
            return render_template('create_squadron.html', edit=True, squadron_id=squadron_id, squadron=squadron)
        # Update structure
        squadron['name'] = name
        squadron['aircraft_type'] = aircraft_type
        squadron['tail_numbers'] = [{"tail": t.strip()} for t in tail_numbers if t.strip()]
        squadron['callsigns'] = [c.strip() for c in callsigns if c.strip()]
        squadrons[squadron_id] = squadron
        try:
            with open(squadrons_path, 'w') as f:
                json.dump(squadrons, f, indent=2)
            flash("Squadron updated.", "success")
        except Exception as e:
            flash(f"Error saving squadron: {e}", "danger")
        return redirect(url_for('admin.list_squadrons'))
    # Prepopulate form fields
    tail_numbers_str = ', '.join([t['tail'] for t in squadron.get('tail_numbers', [])])
    callsigns_str = ', '.join(squadron.get('callsigns', []))
    return render_template('create_squadron.html', edit=True, squadron_id=squadron_id, squadron=squadron, tail_numbers_str=tail_numbers_str, callsigns_str=callsigns_str)

@admin_bp.route('/squadron/delete/<squadron_id>', methods=['POST'])
@admin_required
def delete_squadron(squadron_id):
    """
    Delete a squadron by ID.
    """
    import json
    from flask import current_app, redirect, url_for, flash
    squadrons_path = current_app.config.get('SQUADRONS_PATH', '/var/www/beta.ajac.no/config/squadrons.json')
    try:
        with open(squadrons_path, 'r') as f:
            squadrons = json.load(f)
        if squadron_id in squadrons:
            del squadrons[squadron_id]
            with open(squadrons_path, 'w') as f:
                json.dump(squadrons, f, indent=2)
            flash("Squadron deleted.", "success")
        else:
            flash("Squadron not found.", "danger")
    except Exception as e:
        flash(f"Error deleting squadron: {e}", "danger")
    return redirect(url_for('admin.list_squadrons'))
