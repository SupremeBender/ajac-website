"""
Squadron Template Manager
Handles squadron template inheritance and campaign-specific overrides
"""
import json
import os
import logging
import time
from typing import Dict, List, Any, Optional
from utils.cache import get_cached_json

logger = logging.getLogger(__name__)

class SquadronManager:
    """Manages squadron templates and campaign-specific inheritance"""
    
    def __init__(self):
        self.templates_path = os.path.join(os.path.dirname(__file__), '../instance/data/squadron_templates/squadron_templates.json')
        self._cached_templates = None
        self._cached_inheritance_rules = None
        self._cache_timestamp = 0
    
    def get_squadron_templates(self) -> Dict[str, Any]:
        """Load squadron templates with caching - load once per request cycle"""
        try:
            current_time = time.time()
            # Cache for 5 seconds to avoid multiple file reads in same request
            if (self._cached_templates is None or 
                current_time - self._cache_timestamp > 5):
                
                templates_data = get_cached_json(self.templates_path)
                self._cached_templates = templates_data.get('templates', {})
                self._cached_inheritance_rules = templates_data.get('_inheritance_rules', {})
                self._cache_timestamp = current_time
                
            return self._cached_templates
        except Exception as e:
            logger.error(f"Failed to load squadron templates: {e}")
            return {}
    
    def get_squadron_for_campaign(self, squadron_id: str, campaign_overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get squadron configuration for a specific campaign with inheritance
        
        Args:
            squadron_id: The squadron ID (e.g., "331", "440")
            campaign_overrides: Campaign-specific overrides from campaign.json
            
        Returns:
            Complete squadron configuration with campaign overrides applied
        """
        templates = self.get_squadron_templates()
        
        if squadron_id not in templates:
            logger.error(f"Squadron template {squadron_id} not found")
            return {}
        
        # Start with base template
        squadron_config = self._deep_copy(templates[squadron_id])
        
        # Apply campaign-specific overrides if provided
        if campaign_overrides and squadron_id in campaign_overrides:
            overrides = campaign_overrides[squadron_id]
            squadron_config = self._apply_overrides(squadron_config, overrides)
        
        return squadron_config
    
    def get_all_squadrons_for_campaign(self, campaign_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get all squadron configurations for a campaign - OPTIMIZED for batch processing
        
        Args:
            campaign_data: Full campaign data including squadron overrides
            
        Returns:
            Dictionary of squadron_id -> squadron_config
        """
        # Load templates once for entire batch
        templates = self.get_squadron_templates()
        campaign_overrides = None
        
        if campaign_data and 'squadron_overrides' in campaign_data:
            campaign_overrides = campaign_data['squadron_overrides']
        
        result = {}
        
        # Process all squadrons in one batch to avoid multiple cache calls
        for squadron_id in templates.keys():
            # Use cached templates instead of calling get_squadron_for_campaign
            squadron_config = self._deep_copy(templates[squadron_id])
            
            # Apply campaign-specific overrides if provided
            if campaign_overrides and squadron_id in campaign_overrides:
                overrides = campaign_overrides[squadron_id]
                squadron_config = self._apply_overrides(squadron_config, overrides)
            
            result[squadron_id] = squadron_config
        
        return result
    
    def _deep_copy(self, obj: Any) -> Any:
        """Deep copy an object"""
        if isinstance(obj, dict):
            return {k: self._deep_copy(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._deep_copy(item) for item in obj]
        else:
            return obj
    
    def _apply_overrides(self, base_config: Dict[str, Any], overrides: Dict[str, Any]) -> Dict[str, Any]:
        """
        Apply campaign-specific overrides to base squadron configuration
        Follows inheritance rules defined in squadron_templates.json
        """
        result = self._deep_copy(base_config)
        
        # Use cached inheritance rules instead of reloading
        if self._cached_inheritance_rules is None:
            self.get_squadron_templates()  # This will load and cache the rules
            
        inheritance_rules = self._cached_inheritance_rules or {}
        overridable_fields = inheritance_rules.get('overridable_fields', [])
        extensible_fields = inheritance_rules.get('extensible_fields', [])
        
        for field_path, value in overrides.items():
            if self._is_field_overridable(field_path, overridable_fields):
                self._set_nested_field(result, field_path, value)
            elif self._is_field_extensible(field_path, extensible_fields):
                self._extend_nested_field(result, field_path, value)
            # Removed warning logging to reduce noise and improve performance
        
        return result
    
    def _is_field_overridable(self, field_path: str, overridable_fields: List[str]) -> bool:
        """Check if a field can be completely overridden"""
        return any(field_path.startswith(allowed) for allowed in overridable_fields)
    
    def _is_field_extensible(self, field_path: str, extensible_fields: List[str]) -> bool:
        """Check if a field can be extended (e.g., adding to lists)"""
        return any(field_path.startswith(allowed) for allowed in extensible_fields)
    
    def _set_nested_field(self, obj: Dict[str, Any], field_path: str, value: Any) -> None:
        """Set a nested field value using dot notation"""
        keys = field_path.split('.')
        current = obj
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        current[keys[-1]] = value
    
    def _extend_nested_field(self, obj: Dict[str, Any], field_path: str, value: Any) -> None:
        """Extend a nested field (for lists/arrays)"""
        keys = field_path.split('.')
        current = obj
        
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
        
        final_key = keys[-1]
        if final_key not in current:
            current[final_key] = []
        
        if isinstance(current[final_key], list) and isinstance(value, list):
            # Extend list with new values (avoid duplicates)
            for item in value:
                if item not in current[final_key]:
                    current[final_key].append(item)
        elif isinstance(value, list):
            current[final_key] = value
        else:
            current[final_key] = [value]
    
    def validate_squadron_config(self, squadron_id: str, config: Dict[str, Any]) -> bool:
        """
        Validate a squadron configuration
        
        Args:
            squadron_id: Squadron identifier
            config: Squadron configuration to validate
            
        Returns:
            True if valid, False otherwise
        """
        required_fields = ['name', 'aircraft_type', 'callsigns']
        
        for field in required_fields:
            if field not in config:
                logger.error(f"Squadron {squadron_id} missing required field: {field}")
                return False
        
        # Validate aircraft inventory if present
        if 'aircraft_inventory' in config:
            inventory = config['aircraft_inventory']
            if 'tail_numbers' in inventory:
                if not isinstance(inventory['tail_numbers'], list):
                    logger.error(f"Squadron {squadron_id} tail_numbers must be a list")
                    return False
        
        return True
    
    def get_available_aircraft_for_squadron(self, squadron_id: str, base_filter: Optional[str] = None, 
                                          campaign_data: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Get available aircraft for a squadron with optional base filtering
        
        Args:
            squadron_id: Squadron identifier
            base_filter: Optional base to filter aircraft by location
            campaign_data: Campaign data for overrides
            
        Returns:
            List of available aircraft with metadata
        """
        squadron_config = self.get_squadron_for_campaign(squadron_id, 
                                                        campaign_data.get('squadron_overrides') if campaign_data else None)
        
        aircraft_list = []
        
        if 'aircraft_inventory' in squadron_config:
            inventory = squadron_config['aircraft_inventory']
            tail_numbers = inventory.get('tail_numbers', [])
            aircraft_type = squadron_config.get('aircraft_type', 'UNKNOWN')
            default_base = squadron_config.get('default_base', 'UNKNOWN')
            
            for tail in tail_numbers:
                tail_number = tail if isinstance(tail, str) else tail.get('tail', str(tail))
                
                aircraft_info = {
                    'tail': tail_number,
                    'type': aircraft_type,
                    'squadron': squadron_id,
                    'location': default_base,  # Default location, could be overridden by campaign
                    'maintenance_state': inventory.get('maintenance_state', 100),
                    'special_requirements': inventory.get('special_requirements', [])
                }
                
                # Apply base filter if specified
                if base_filter is None or aircraft_info['location'] == base_filter:
                    aircraft_list.append(aircraft_info)
        
        return aircraft_list
    
    def get_campaign_squadrons(self, campaign_id: str, campaign_squadrons) -> Dict[str, Any]:
        """
        Get squadrons for a specific campaign with template enhancements - supports both dict (new) and list (legacy) formats.
        
        Args:
            campaign_id: Campaign identifier
            campaign_squadrons: Dict (new format) or list (legacy) of squadron data from campaign
            
        Returns:
            Dictionary of squadron_id -> squadron config (campaign-specific, not template)
        """
        result = {}
        # If campaign_squadrons is a dict (new format), process directly
        if isinstance(campaign_squadrons, dict):
            for squadron_id, sq_data in campaign_squadrons.items():
                # Copy all relevant info directly from the campaign's squadrons.json
                result[squadron_id] = dict(sq_data)
                # Ensure the squadron ID is present in the dict
                result[squadron_id]['id'] = squadron_id
            return result
        # If campaign_squadrons is a list (legacy), fallback to old logic
        elif isinstance(campaign_squadrons, list):
            templates = self.get_squadron_templates()
            from utils.storage import load_campaign
            campaign_data = load_campaign(campaign_id)
            campaign_overrides = campaign_data.get('squadron_overrides', {}) if campaign_data else {}
            for squadron_data in campaign_squadrons:
                squadron_id = squadron_data.get('id')
                if not squadron_id:
                    continue
                if squadron_id not in templates:
                    logger.warning(f"No template found for squadron {squadron_id}, skipping")
                    continue
                enhanced_config = self._deep_copy(templates[squadron_id])
                if squadron_id in campaign_overrides:
                    enhanced_config = self._apply_overrides(enhanced_config, campaign_overrides[squadron_id])
                squadron_base = squadron_data.get('base') or enhanced_config.get('default_base')
                tail_numbers = []
                if 'tail_numbers' in enhanced_config:
                    tail_numbers = enhanced_config['tail_numbers']
                elif 'aircraft_inventory' in enhanced_config and 'tail_numbers' in enhanced_config['aircraft_inventory']:
                    inventory_tails = enhanced_config['aircraft_inventory']['tail_numbers']
                    tail_numbers = [{"tail": tail} if isinstance(tail, str) else tail for tail in inventory_tails]
                result[squadron_id] = {
                    'id': squadron_id,
                    'name': enhanced_config.get('name'),
                    'aircraft_type': enhanced_config.get('aircraft_type'),
                    'callsigns': enhanced_config.get('callsigns', []),
                    'base': squadron_base,
                    'tail_numbers': tail_numbers
                }
            return result
        else:
            logger.error(f"Unknown campaign_squadrons format: {type(campaign_squadrons)}")
            return {}
        

# Global instance for easy access
squadron_manager = SquadronManager()

# Convenience functions for backward compatibility
def get_squadrons(campaign_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get all squadrons for a campaign (backward compatible)"""
    return squadron_manager.get_all_squadrons_for_campaign(campaign_data)

def get_squadron_config(squadron_id: str, campaign_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Get configuration for a specific squadron"""
    campaign_overrides = campaign_data.get('squadron_overrides') if campaign_data else None
    return squadron_manager.get_squadron_for_campaign(squadron_id, campaign_overrides)
