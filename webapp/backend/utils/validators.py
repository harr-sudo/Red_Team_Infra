"""
Validators
Validation utilities for configuration and inputs
"""

import re
from typing import Dict, List, Tuple

# Deployment types that are GOAD-only (auto-generate their own SSH keys)
GOAD_ONLY_DEPLOYMENT_TYPES = [
    'goad-mini', 'goad-minilab', 'goad-light', 'goad-sccm', 'goad-full', 'goad-nha'
]

# Deployment types that require a domain name
DOMAIN_REQUIRED_DEPLOYMENT_TYPES = [
    'c2-adhoc', 'c2-purple', 'c2-full',
    'combined-adhoc-mini', 'combined-adhoc-light', 'combined-full-full'
]


class ConfigValidator:
    """Validator for Terraform configuration"""
    
    @staticmethod
    def is_goad_only_deployment(deployment_type: str) -> bool:
        """Check if deployment type is GOAD-only (auto-generates SSH keys)"""
        return deployment_type in GOAD_ONLY_DEPLOYMENT_TYPES
    
    @staticmethod
    def requires_domain(deployment_type: str) -> bool:
        """Check if deployment type requires domain configuration"""
        return deployment_type in DOMAIN_REQUIRED_DEPLOYMENT_TYPES
    
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
    def validate_domain(domain: str) -> bool:
        """Validate domain name format"""
        if not domain or domain.strip() == "":
            return False
        
        # Basic domain validation pattern
        pattern = r'^([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}$'
        return bool(re.match(pattern, domain.lower()))
    
    @staticmethod
    def validate_domain_config(config: Dict) -> Tuple[bool, List[str]]:
        """Validate domain configuration (only for deployments that require it)"""
        errors = []
        
        deployment_type = config.get('deployment_type', '')
        
        # GOAD-only deployments don't require domain configuration
        if ConfigValidator.is_goad_only_deployment(deployment_type):
            return True, []
        
        # C2 and Combined deployments require domain
        if ConfigValidator.requires_domain(deployment_type):
            primary_domain = config.get('primary_domain_name', '').strip()
            if not primary_domain:
                errors.append("primary_domain_name is required for C2 infrastructure")
            elif not ConfigValidator.validate_domain(primary_domain):
                errors.append(f"Invalid primary_domain_name format: {primary_domain}")
            
            # Backup domains are recommended but not strictly required
            backup_domains = config.get('backup_domains', [])
            if isinstance(backup_domains, list) and len(backup_domains) > 0:
                for i, backup in enumerate(backup_domains):
                    if isinstance(backup, dict):
                        backup_domain = backup.get('domain_name', '').strip()
                        if backup_domain and not ConfigValidator.validate_domain(backup_domain):
                            errors.append(f"Invalid backup_domains[{i}].domain_name format: {backup_domain}")
        
        return len(errors) == 0, errors
    
    @staticmethod
    def validate_config(config: Dict) -> Tuple[bool, List[str]]:
        """Validate complete configuration"""
        errors = []
        
        deployment_type = config.get('deployment_type', '')
        is_goad_only = ConfigValidator.is_goad_only_deployment(deployment_type)
        
        # Required fields for ALL deployments
        if not config.get('project_name'):
            errors.append("project_name is required")
        
        if not config.get('environment'):
            errors.append("environment is required")
        
        # key_pair_name is only required for C2 and Combined deployments
        # GOAD-only deployments auto-generate their own SSH keys
        if not is_goad_only and not config.get('key_pair_name'):
            errors.append("key_pair_name is required for C2/Combined deployments (GOAD-only auto-generates keys)")
        
        # Validate engagement type
        engagement_type = config.get('engagement_type', '')
        if engagement_type and not ConfigValidator.validate_engagement_type(engagement_type):
            errors.append(f"Invalid engagement_type: {engagement_type}")
        
        # Validate deployment mode
        deployment_mode = config.get('c2_deployment_mode', '')
        if deployment_mode and not ConfigValidator.validate_deployment_mode(deployment_mode):
            errors.append(f"Invalid c2_deployment_mode: {deployment_mode}")
        
        # management_cidr_blocks is REQUIRED for ALL deployments
        # Without it, security groups won't allow SSH/RDP/WinRM/CS access
        management_cidr = config.get('management_cidr_blocks', [])
        if not management_cidr:
            errors.append("management_cidr_blocks is required (your IP address for SSH/RDP/CS access, e.g., '1.2.3.4/32')")
        else:
            valid, error = ConfigValidator.validate_cidr_blocks(management_cidr)
            if not valid:
                errors.append(error)
        
        # Validate VPC CIDR (only for C2/Combined which create their own VPC)
        if not is_goad_only:
            vpc_cidr = config.get('vpc_cidr', '')
            if vpc_cidr and not ConfigValidator.validate_ip_cidr(vpc_cidr):
                errors.append(f"Invalid VPC CIDR: {vpc_cidr}")
        
        # Validate domain configuration (conditional based on deployment type)
        domain_valid, domain_errors = ConfigValidator.validate_domain_config(config)
        if not domain_valid:
            errors.extend(domain_errors)
        
        return len(errors) == 0, errors

