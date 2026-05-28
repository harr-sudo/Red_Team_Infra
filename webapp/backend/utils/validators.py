"""
Validators
Validation utilities for configuration and inputs
"""

import re
from typing import Dict, List, Tuple

# Deployment types that are GOAD-only (auto-generate their own SSH keys)
GOAD_ONLY_DEPLOYMENT_TYPES = [
    'goad-mini', 'goad-light', 'goad-sccm', 'goad-full', 'goad-nha'
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

        # OPSEC: Block overly permissive CIDRs that expose management ports to the internet
        dangerous_cidrs = ["0.0.0.0/0", "::/0"]

        for cidr in cidr_blocks:
            if not ConfigValidator.validate_ip_cidr(cidr):
                return False, f"Invalid CIDR block: {cidr}"
            if cidr in dangerous_cidrs:
                return False, f"CIDR block {cidr} is too permissive for management access. Use your specific IP (e.g., 1.2.3.4/32)"

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
                    # Support both plain strings and objects with domain_name key
                    if isinstance(backup, dict):
                        backup_domain = backup.get('domain_name', '').strip()
                    elif isinstance(backup, str):
                        backup_domain = backup.strip()
                    else:
                        backup_domain = ''
                    if backup_domain and not ConfigValidator.validate_domain(backup_domain):
                        errors.append(f"Invalid backup_domains[{i}] format: {backup_domain}")
        
        # Validate domain fronting requirements
        enable_domain_fronting = config.get('enable_domain_fronting', False)
        if enable_domain_fronting:
            if not config.get('primary_domain_name', '').strip():
                errors.append("enable_domain_fronting requires primary_domain_name to be set")

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
        
        # 2026-05-28 — Real-pipeline audit fix (HIGH #12): `engagement_type`
        # was renamed to `deployment_type` long ago but legacy tfvars +
        # `templates` endpoint still carry it. Previously this validator
        # bounced the entire save with "Invalid engagement_type" for any
        # leftover field, breaking template loads. Strip + ignore instead.
        if 'engagement_type' in config and 'deployment_type' not in config:
            # Promote silently for backwards compat if the new field is absent.
            config['deployment_type'] = config.pop('engagement_type')
        elif 'engagement_type' in config:
            config.pop('engagement_type', None)
        
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
        
        # Validate instance types (soft check — warn on non-standard types)
        valid_c2_types = ['t3.small', 't2.medium', 't2.large', 't3.medium', 't3.large', 't3.xlarge', 'm5.large', 'm5.xlarge']
        valid_redirector_types = ['t2.micro', 't2.small', 't3.micro', 't3.small', 't3.medium']
        valid_bastion_types = ['t2.micro', 't2.small', 't3.micro', 't3.small']

        c2_type = config.get('c2_server_instance_type', '')
        if c2_type and c2_type not in valid_c2_types:
            errors.append(f"Unusual c2_server_instance_type: {c2_type}. Common: {', '.join(valid_c2_types[:4])}")

        redirector_type = config.get('proxy_redirector_instance_type', '')
        if redirector_type and redirector_type not in valid_redirector_types:
            errors.append(f"Unusual proxy_redirector_instance_type: {redirector_type}. Common: {', '.join(valid_redirector_types[:3])}")

        # Validate VPC CIDR (only for C2/Combined which create their own VPC)
        if not is_goad_only:
            vpc_cidr = config.get('vpc_cidr', '')
            if vpc_cidr and not ConfigValidator.validate_ip_cidr(vpc_cidr):
                errors.append(f"Invalid VPC CIDR: {vpc_cidr}")
        
        # Validate domain configuration (conditional based on deployment type)
        domain_valid, domain_errors = ConfigValidator.validate_domain_config(config)
        if not domain_valid:
            errors.extend(domain_errors)

        # Validate attack box configuration
        attack_box_valid, attack_box_errors = ConfigValidator.validate_attack_box_config(config)
        if not attack_box_valid:
            errors.extend(attack_box_errors)

        # Validate SSL / Let's Encrypt admin email
        # Required when: C2/Combined deployment + SSL enabled + letsencrypt provider + not domain fronting
        enable_ssl = config.get('enable_ssl', True)
        ssl_provider = config.get('ssl_provider', 'letsencrypt')
        enable_domain_fronting = config.get('enable_domain_fronting', False)

        if not is_goad_only and enable_ssl and ssl_provider == 'letsencrypt' and not enable_domain_fronting:
            admin_email = config.get('admin_email', '').strip()
            if not admin_email:
                errors.append("admin_email is required for Let's Encrypt SSL (use a burner email for OPSEC)")

        # Validate passwords (soft — warn on weak, don't block)
        cs_pw = config.get('cs_teamserver_password', '')
        if cs_pw and len(cs_pw) < 8:
            errors.append("cs_teamserver_password must be at least 8 characters")

        ab_pw = config.get('attack_box_admin_password', '')
        if ab_pw and len(ab_pw) < 8:
            errors.append("attack_box_admin_password must be at least 8 characters")

        # Validate file portal configuration
        fp_valid, fp_errors = ConfigValidator.validate_file_portal_config(config)
        if not fp_valid:
            errors.extend(fp_errors)

        return len(errors) == 0, errors

    @staticmethod
    def validate_attack_box_config(config: Dict) -> Tuple[bool, List[str]]:
        """Validate attack box configuration"""
        errors = []

        enable_attack_box = config.get('enable_attack_box', True)
        if not enable_attack_box:
            return True, []

        # Validate instance type
        valid_instance_types = ['t2.large', 't3.large', 't3.xlarge', 'm5.large']
        instance_type = config.get('attack_box_instance_type', 't2.large')
        if instance_type and instance_type not in valid_instance_types:
            errors.append(f"Invalid attack_box_instance_type: {instance_type}. Must be one of: {', '.join(valid_instance_types)}")

        # Validate disk size
        disk_size = config.get('attack_box_root_volume_size', 100)
        if isinstance(disk_size, (int, float)):
            if disk_size < 50 or disk_size > 500:
                errors.append(f"attack_box_root_volume_size must be between 50 and 500 GB (got {disk_size})")

        return len(errors) == 0, errors

    @staticmethod
    def validate_file_portal_config(config: Dict) -> Tuple[bool, List[str]]:
        """Validate file portal configuration."""
        errors = []
        enable = config.get('enable_file_portal', False)
        if not enable:
            return True, errors

        username = config.get('portal_username', '').strip()
        if not username:
            errors.append("portal_username is required when file portal is enabled")
        elif len(username) < 3:
            errors.append("portal_username must be at least 3 characters")
        elif not re.match(r'^[a-zA-Z0-9_-]+$', username):
            errors.append("portal_username can only contain alphanumeric characters, hyphens, and underscores")

        password = config.get('portal_password', '').strip()
        if not password:
            errors.append("portal_password is required when file portal is enabled")
        elif len(password) < 8:
            errors.append("portal_password must be at least 8 characters")

        timeout = config.get('portal_session_timeout', 30)
        if not isinstance(timeout, (int, float)) or timeout < 1 or timeout > 1440:
            errors.append("portal_session_timeout must be between 1 and 1440 minutes")

        return len(errors) == 0, errors

