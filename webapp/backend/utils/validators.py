"""
Validators
Validation utilities for configuration and inputs
"""

import re
from typing import Dict, List, Tuple

class ConfigValidator:
    """Validator for Terraform configuration"""
    
    @staticmethod
    def validate_ip_cidr(cidr: str) -> bool:
        """Validate IP CIDR block format"""
        pattern = r'^(\d{1,3}\.){3}\d{1,3}/\d{1,2}$'
        if not re.match(pattern, cidr):
            return False
        
        parts = cidr.split('/')
        ip = parts[0]
        mask = int(parts[1])
        
        if mask < 0 or mask > 32:
            return False
        
        octets = ip.split('.')
        if len(octets) != 4:
            return False
        
        for octet in octets:
            try:
                num = int(octet)
                if num < 0 or num > 255:
                    return False
            except ValueError:
                return False
        
        return True
    
    @staticmethod
    def validate_cidr_blocks(cidr_blocks: List[str]) -> Tuple[bool, str]:
        """Validate list of CIDR blocks"""
        if not cidr_blocks:
            return False, "At least one CIDR block is required"
        
        for cidr in cidr_blocks:
            if not ConfigValidator.validate_ip_cidr(cidr):
                return False, f"Invalid CIDR block: {cidr}"
        
        return True, ""
    
    @staticmethod
    def validate_subnet_cidr(cidr: str, vpc_cidr: str) -> Tuple[bool, str]:
        """Validate subnet CIDR is within VPC CIDR"""
        # Simple validation - could be enhanced
        if not ConfigValidator.validate_ip_cidr(cidr):
            return False, f"Invalid subnet CIDR: {cidr}"
        
        # TODO: Add proper CIDR containment check
        return True, ""
    
    @staticmethod
    def validate_engagement_type(engagement_type: str) -> bool:
        """Validate engagement type"""
        valid_types = ["", "adhoc", "purple-team", "full-red-team"]
        return engagement_type in valid_types
    
    @staticmethod
    def validate_deployment_mode(mode: str) -> bool:
        """Validate deployment mode"""
        valid_modes = ["", "single", "redundancy", "phases"]
        return mode in valid_modes
    
    @staticmethod
    def validate_config(config: Dict) -> Tuple[bool, List[str]]:
        """Validate complete configuration"""
        errors = []
        
        # Required fields
        if not config.get('project_name'):
            errors.append("project_name is required")
        
        if not config.get('environment'):
            errors.append("environment is required")
        
        if not config.get('key_pair_name'):
            errors.append("key_pair_name is required")
        
        # Validate engagement type
        engagement_type = config.get('engagement_type', '')
        if engagement_type and not ConfigValidator.validate_engagement_type(engagement_type):
            errors.append(f"Invalid engagement_type: {engagement_type}")
        
        # Validate deployment mode
        deployment_mode = config.get('c2_deployment_mode', '')
        if deployment_mode and not ConfigValidator.validate_deployment_mode(deployment_mode):
            errors.append(f"Invalid c2_deployment_mode: {deployment_mode}")
        
        # Validate CIDR blocks
        management_cidr = config.get('management_cidr_blocks', [])
        if management_cidr:
            valid, error = ConfigValidator.validate_cidr_blocks(management_cidr)
            if not valid:
                errors.append(error)
        
        # Validate VPC CIDR
        vpc_cidr = config.get('vpc_cidr', '')
        if vpc_cidr and not ConfigValidator.validate_ip_cidr(vpc_cidr):
            errors.append(f"Invalid VPC CIDR: {vpc_cidr}")
        
        return len(errors) == 0, errors

