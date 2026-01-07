"""
Configuration Parser
Utilities for parsing and managing terraform.tfvars files
"""

import re
from pathlib import Path
from typing import Dict, Any, Optional

class ConfigParser:
    """Parser for Terraform variable files"""
    
    @staticmethod
    def parse_tfvars(file_path: Path) -> Dict[str, Any]:
        """Parse terraform.tfvars file into dictionary"""
        if not file_path.exists():
            return {}
        
        config = {}
        with open(file_path, 'r') as f:
            content = f.read()
        
        # Simple parser for HCL-like syntax
        # Match key = value patterns
        patterns = [
            # String values: key = "value"
            (r'(\w+)\s*=\s*"([^"]*)"', str),
            # Number values: key = 123
            (r'(\w+)\s*=\s*(\d+)', int),
            # Boolean values: key = true/false
            (r'(\w+)\s*=\s*(true|false)', lambda x: x == 'true'),
            # List values: key = ["value1", "value2"]
            (r'(\w+)\s*=\s*\[(.*?)\]', lambda x: [v.strip().strip('"') for v in x.split(',')]),
        ]
        
        for pattern, converter in patterns:
            matches = re.finditer(pattern, content)
            for match in matches:
                key = match.group(1)
                value = match.group(2)
                try:
                    config[key] = converter(value)
                except:
                    config[key] = value
        
        return config
    
    @staticmethod
    def generate_tfvars(config: Dict[str, Any]) -> str:
        """Generate terraform.tfvars content from dictionary"""
        lines = []
        
        # Group by sections
        sections = {
            'AWS Configuration': ['aws_region', 'aws_profile'],
            'Project Configuration': ['project_name', 'environment', 'engagement_type'],
            'VPC Configuration': ['vpc_cidr', 'availability_zones', 'public_subnet_cidrs', 'private_subnet_cidrs', 'enable_nat_gateway'],
            'Security Configuration': ['management_cidr_blocks', 'ssh_port', 'c2_server_port'],
            'Key Pair Configuration': ['key_pair_name'],
            'Domain Configuration': ['primary_domain_name', 'primary_domain_hosted_zone_id', 'backup_domains', 'c2_subdomain', 'www_subdomain', 'cdn_subdomain', 'dns_provider', 'enable_dns_validation'],
            'C2 Team Server Configuration': ['c2_deployment_mode', 'c2_server_count', 'c2_server_instance_type', 'c2_server_ami_id', 'c2_server_root_volume_size', 'c2_server_enable_elastic_ips', 'c2_server_iam_instance_profile_name', 'c2_server_user_data'],
            'Proxy/Redirector Configuration': ['proxy_redirector_count', 'proxy_redirector_instance_type', 'proxy_redirector_ami_id', 'proxy_redirector_root_volume_size', 'proxy_redirector_iam_instance_profile_name', 'proxy_redirector_user_data'],
            'Monitoring Configuration': ['enable_detailed_monitoring'],
            'Tags': ['tags'],
        }
        
        for section_name, keys in sections.items():
            section_vars = {k: v for k, v in config.items() if k in keys}
            if section_vars:
                lines.append(f"# {section_name}")
                for key, value in section_vars.items():
                    lines.append(ConfigParser._format_value(key, value))
                lines.append("")
        
        # Add remaining variables
        remaining = {k: v for k, v in config.items() if k not in [item for sublist in sections.values() for item in sublist]}
        if remaining:
            lines.append("# Other Configuration")
            for key, value in remaining.items():
                lines.append(ConfigParser._format_value(key, value))
        
        return "\n".join(lines)
    
    @staticmethod
    def _format_value(key: str, value: Any) -> str:
        """Format a key-value pair for terraform.tfvars"""
        if isinstance(value, str):
            return f'{key} = "{value}"'
        elif isinstance(value, bool):
            return f'{key} = {str(value).lower()}'
        elif isinstance(value, (int, float)):
            return f'{key} = {value}'
        elif isinstance(value, list):
            # Check if it's a list of dicts (like backup_domains)
            if value and all(isinstance(item, dict) for item in value):
                items = []
                for item in value:
                    obj_items = []
                    for k, v in item.items():
                        if isinstance(v, str):
                            obj_items.append(f'    {k} = "{v}"')
                        else:
                            obj_items.append(f'    {k} = {v}')
                    items.append('  {\n' + '\n'.join(obj_items) + '\n  }')
                return f'{key} = [\n' + ',\n'.join(items) + '\n]'
            elif all(isinstance(item, str) for item in value):
                items = ', '.join(f'"{item}"' for item in value)
                return f'{key} = [{items}]'
            else:
                items = ', '.join(str(item) for item in value)
                return f'{key} = [{items}]'
        elif isinstance(value, dict):
            # Format as HCL object
            items = []
            for k, v in value.items():
                items.append(f'  {k} = {ConfigParser._format_value("", v).replace(" = ", "")}')
            return f'{key} = {{\n' + ',\n'.join(items) + '\n}'
        else:
            return f'{key} = {value}'

