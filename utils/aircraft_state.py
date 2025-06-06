#!/usr/bin/env python3
"""
Aircraft State Management System

This module provides campaign-level aircraft state tracking that integrates with
the squadron template system. It replaces the global aircraft.json with a 
campaign-specific approach.

Key Features:
- Generates individual aircraft state during campaign creation
- Tracks tail number locations, maintenance states, and special qualifications  
- Integrates with existing squadron templates
- Supports cross-base validation for flight creation
"""

import json
import logging
import os
from typing import Dict, Any, Optional, List
from utils.storage import get_campaign_dir
from utils.squadron_manager import squadron_manager

logger = logging.getLogger(__name__)

def generate_campaign_aircraft_state(campaign_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Generate individual aircraft state for a campaign based on squadron templates
    and base assignments.
    
    Args:
        campaign_data: Campaign configuration including squadrons and their assigned bases
        
    Returns:
        Dictionary mapping tail numbers to aircraft state:
        {
            "tail_number": {
                "type": "F-16C",
                "squadron": "331", 
                "location": "ENBO",
                "maint_state": 100,
                "requirement": "QUAL"  # optional
            }
        }
    """
    logger.info(f"Generating aircraft state for campaign: {campaign_data.get('name', 'Unknown')}")
    
    aircraft_state = {}
    
    # Get squadron templates
    try:
        templates = squadron_manager.get_squadron_templates()
    except Exception as e:
        logger.error(f"Failed to load squadron templates: {e}")
        return aircraft_state
    
    # Process each squadron in the campaign
    for squadron_config in campaign_data.get('squadrons', []):
        squadron_id = squadron_config.get('id')
        assigned_base = squadron_config.get('base')
        
        if not squadron_id or not assigned_base:
            logger.warning(f"Skipping squadron config with missing id or base: {squadron_config}")
            continue
            
        # Get squadron template
        template = templates.get(squadron_id)
        if not template:
            logger.warning(f"No template found for squadron {squadron_id}")
            continue
            
        # Get tail numbers from template
        tail_numbers = template.get('tail_numbers', [])
        aircraft_type = template.get('aircraft_type', 'UNKNOWN')
        
        logger.debug(f"Processing {len(tail_numbers)} aircraft for squadron {squadron_id} at {assigned_base}")
        
        # Generate aircraft state for each tail number
        for tail_num in tail_numbers:
            # Handle both string and dict formats for tail numbers
            if isinstance(tail_num, dict):
                tail = tail_num.get('tail', str(tail_num))
            else:
                tail = str(tail_num)
                
            # Create aircraft state entry
            aircraft_state[tail] = {
                "type": aircraft_type,
                "squadron": squadron_id,
                "location": assigned_base,
                "maint_state": 100  # Default to fully operational
            }
            
            # Add special requirements based on aircraft type or squadron
            if aircraft_type == "F/A-18C" and squadron_id == "440":
                # Carrier aircraft require special qualifications (from reference data)
                aircraft_state[tail]["requirement"] = "QUAL"
    
    logger.info(f"Generated aircraft state for {len(aircraft_state)} aircraft across {len(campaign_data.get('squadrons', []))} squadrons")
    return aircraft_state

def save_campaign_aircraft_state(campaign_id: str, aircraft_state: Dict[str, Dict[str, Any]]) -> None:
    """
    Save aircraft state for a campaign.
    
    Args:
        campaign_id: Campaign identifier
        aircraft_state: Aircraft state data to save
    """
    try:
        campaign_dir = get_campaign_dir(campaign_id)
        aircraft_state_path = os.path.join(campaign_dir, 'aircraft_state.json')
        
        # Ensure campaign directory exists
        os.makedirs(campaign_dir, exist_ok=True)
        
        with open(aircraft_state_path, 'w') as f:
            json.dump(aircraft_state, f, indent=2)
            
        logger.info(f"Saved aircraft state for campaign {campaign_id} ({len(aircraft_state)} aircraft)")
        
    except Exception as e:
        logger.error(f"Failed to save aircraft state for campaign {campaign_id}: {e}")
        raise

def load_campaign_aircraft_state(campaign_id: str) -> Dict[str, Dict[str, Any]]:
    """
    Load aircraft state for a campaign.
    
    Args:
        campaign_id: Campaign identifier
        
    Returns:
        Aircraft state data, empty dict if not found
    """
    try:
        campaign_dir = get_campaign_dir(campaign_id)
        aircraft_state_path = os.path.join(campaign_dir, 'aircraft_state.json')
        
        if not os.path.exists(aircraft_state_path):
            logger.warning(f"No aircraft state file found for campaign {campaign_id}")
            return {}
            
        with open(aircraft_state_path, 'r') as f:
            aircraft_state = json.load(f)
            
        logger.debug(f"Loaded aircraft state for campaign {campaign_id} ({len(aircraft_state)} aircraft)")
        return aircraft_state
        
    except Exception as e:
        logger.error(f"Failed to load aircraft state for campaign {campaign_id}: {e}")
        return {}

def get_aircraft_at_base_for_campaign(campaign_id: str, base_id: str) -> Dict[str, Dict[str, Any]]:
    """
    Get aircraft at a specific base for a campaign.
    
    Args:
        campaign_id: Campaign identifier
        base_id: Base identifier
        
    Returns:
        Dictionary of aircraft at the base
    """
    aircraft_state = load_campaign_aircraft_state(campaign_id)
    
    aircraft_at_base = {
        tail: data for tail, data in aircraft_state.items()
        if data.get("location") == base_id
    }
    
    logger.debug(f"Found {len(aircraft_at_base)} aircraft at base {base_id} for campaign {campaign_id}")
    return aircraft_at_base

def get_squadron_aircraft_for_campaign(campaign_id: str, squadron_id: str, base_id: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Get aircraft for a squadron in a campaign, optionally filtered by base.
    
    Args:
        campaign_id: Campaign identifier
        squadron_id: Squadron identifier
        base_id: Optional base filter
        
    Returns:
        Dictionary of squadron aircraft
    """
    aircraft_state = load_campaign_aircraft_state(campaign_id)
    
    squadron_aircraft = {
        tail: data for tail, data in aircraft_state.items()
        if data.get("squadron") == squadron_id and (not base_id or data.get("location") == base_id)
    }
    
    logger.debug(f"Found {len(squadron_aircraft)} aircraft for squadron {squadron_id} in campaign {campaign_id}")
    return squadron_aircraft

def update_aircraft_state(campaign_id: str, tail_number: str, updates: Dict[str, Any]) -> bool:
    """
    Update specific aircraft state fields.
    
    Args:
        campaign_id: Campaign identifier
        tail_number: Aircraft tail number
        updates: Dictionary of fields to update
        
    Returns:
        True if successful, False otherwise
    """
    try:
        aircraft_state = load_campaign_aircraft_state(campaign_id)
        
        if tail_number not in aircraft_state:
            logger.warning(f"Aircraft {tail_number} not found in campaign {campaign_id}")
            return False
            
        # Update fields
        aircraft_state[tail_number].update(updates)
        
        # Save updated state
        save_campaign_aircraft_state(campaign_id, aircraft_state)
        
        logger.info(f"Updated aircraft {tail_number} in campaign {campaign_id}: {updates}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to update aircraft {tail_number} in campaign {campaign_id}: {e}")
        return False

def migrate_aircraft_state_for_existing_campaign(campaign_id: str) -> bool:
    """
    Generate aircraft state for an existing campaign that doesn't have it yet.
    This can be used to migrate existing campaigns to the new system.
    
    Args:
        campaign_id: Campaign identifier
        
    Returns:
        True if successful, False otherwise
    """
    try:
        from utils.storage import load_campaign
        
        campaign_data = load_campaign(campaign_id)
        if not campaign_data:
            logger.error(f"Campaign {campaign_id} not found")
            return False
            
        # Check if aircraft state already exists
        existing_state = load_campaign_aircraft_state(campaign_id)
        if existing_state:
            logger.info(f"Aircraft state already exists for campaign {campaign_id}")
            return True
            
        # Generate new aircraft state
        aircraft_state = generate_campaign_aircraft_state(campaign_data)
        
        if not aircraft_state:
            logger.warning(f"No aircraft state generated for campaign {campaign_id}")
            return False
            
        # Save the generated state
        save_campaign_aircraft_state(campaign_id, aircraft_state)
        
        logger.info(f"Migrated aircraft state for existing campaign {campaign_id}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to migrate aircraft state for campaign {campaign_id}: {e}")
        return False
