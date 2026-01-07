"""
GOAD Template Processor
=======================
Processes GOAD's Jinja-style templates and generates Terraform-ready files.

GOAD uses placeholders like:
- {{lab_identifier}} - Lab name (e.g., "goad-light")
- {{lab_name}} - Display name (e.g., "GOAD-Light")
- {{ip_range}} - Network prefix (e.g., "192.168.56")
- {{windows_vms}} - VM configuration block
- {{config.get_value(...)}} - Config values

This processor replaces these placeholders with actual values.
"""

import os
import glob
import shutil
import json
import re
from typing import Dict, Optional, Any
from pathlib import Path


# =============================================================================
# GOAD Lab Configurations
# =============================================================================

GOAD_LABS = {
    'GOAD-Mini': {
        'source_dir': 'tools/goad/ad/GOAD-Mini/providers/aws',
        'template_dir': 'tools/goad/template/provider/aws',
        'config_file': 'tools/goad/ad/GOAD-Mini/data/config.json',
        'lab_identifier': 'goad-mini',
        'default_ip_range': '192.168.56',
        'vm_count': 1,
        'domains': 1,
        'forests': 1,
        'description': 'Single DC - sevenkingdoms.local',
    },
    'MINILAB': {
        'source_dir': 'tools/goad/ad/MINILAB/providers/aws',
        'template_dir': 'tools/goad/template/provider/aws',
        'config_file': 'tools/goad/ad/MINILAB/data/config.json',
        'lab_identifier': 'minilab',
        'default_ip_range': '192.168.56',
        'vm_count': 2,
        'domains': 1,
        'forests': 1,
        'description': 'DC + Workstation',
    },
    'GOAD-Light': {
        'source_dir': 'tools/goad/ad/GOAD-Light/providers/aws',
        'template_dir': 'tools/goad/template/provider/aws',
        'config_file': 'tools/goad/ad/GOAD-Light/data/config.json',
        'lab_identifier': 'goad-light',
        'default_ip_range': '192.168.56',
        'vm_count': 3,
        'domains': 2,
        'forests': 1,
        'description': '3 VMs, 1 forest, 2 domains',
    },
    'SCCM': {
        'source_dir': 'tools/goad/ad/SCCM/providers/aws',
        'template_dir': 'tools/goad/template/provider/aws',
        'config_file': 'tools/goad/ad/SCCM/data/config.json',
        'lab_identifier': 'sccm',
        'default_ip_range': '192.168.56',
        'vm_count': 4,
        'domains': 1,
        'forests': 1,
        'description': '4 VMs with SCCM/ConfigMgr',
    },
    'GOAD': {
        'source_dir': 'tools/goad/ad/GOAD/providers/aws',
        'template_dir': 'tools/goad/template/provider/aws',
        'config_file': 'tools/goad/ad/GOAD/data/config.json',
        'lab_identifier': 'goad',
        'default_ip_range': '192.168.56',
        'vm_count': 5,
        'domains': 3,
        'forests': 2,
        'description': '5 VMs, 2 forests, 3 domains',
    },
    'NHA': {
        'source_dir': 'tools/goad/ad/NHA/providers/aws',
        'template_dir': 'tools/goad/template/provider/aws',
        'config_file': 'tools/goad/ad/NHA/data/config.json',
        'lab_identifier': 'nha',
        'default_ip_range': '192.168.56',
        'vm_count': 5,
        'domains': 2,
        'forests': 1,
        'description': '5 VMs, 2 domains - Challenge mode',
    },
}


def get_available_labs() -> Dict[str, Dict]:
    """Return available GOAD lab configurations."""
    return GOAD_LABS


def get_lab_info(lab_type: str) -> Optional[Dict]:
    """Get information about a specific GOAD lab type."""
    return GOAD_LABS.get(lab_type)


def process_goad_templates(
    lab_type: str,
    aws_region: str = 'us-east-1',
    aws_zone: str = 'us-east-1a',
    ip_range: Optional[str] = None,
    output_dir: Optional[str] = None,
    base_path: Optional[str] = None
) -> str:
    """
    Process GOAD Jinja templates and output Terraform-ready files.
    
    Args:
        lab_type: GOAD lab type (e.g., 'GOAD-Light')
        aws_region: AWS region (e.g., 'us-east-1')
        aws_zone: AWS availability zone (e.g., 'us-east-1a')
        ip_range: Override IP range (default from GOAD_LABS)
        output_dir: Output directory (default: terraform/modules/goad/generated)
        base_path: Base path for the project (default: current directory)
    
    Returns:
        Path to generated Terraform files
    """
    if lab_type not in GOAD_LABS:
        raise ValueError(f"Unknown GOAD lab type: {lab_type}. Available: {list(GOAD_LABS.keys())}")
    
    config = GOAD_LABS[lab_type]
    base_path = base_path or os.getcwd()
    
    source_dir = os.path.join(base_path, config['source_dir'])
    template_dir = os.path.join(base_path, config['template_dir'])
    ip_range = ip_range or config['default_ip_range']
    lab_identifier = config['lab_identifier']
    
    output_dir = output_dir or os.path.join(base_path, 'terraform/modules/goad/generated')
    
    # Clear and recreate output directory
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    
    # Define replacements
    replacements = {
        '{{lab_identifier}}': lab_identifier,
        '{{lab_name}}': lab_type,
        '{{ip_range}}': ip_range,
        "{{config.get_value('aws', 'aws_region', 'eu-west-3')}}": aws_region,
        "{{config.get_value('aws', 'aws_zone', 'eu-west-3c')}}": aws_zone,
    }
    
    # Read Windows VM config from lab-specific file
    windows_vms_content = _read_windows_vms(source_dir, ip_range)
    replacements['{{windows_vms}}'] = windows_vms_content
    
    # Process template files
    _process_template_files(template_dir, output_dir, replacements)
    
    # Process lab-specific files (may override templates)
    _process_lab_specific_files(source_dir, output_dir, replacements)
    
    # Create additional helper files
    _create_helper_files(output_dir, lab_type, config, ip_range)
    
    return output_dir


def _read_windows_vms(source_dir: str, ip_range: str) -> str:
    """Read and process the windows.tf VM configuration."""
    windows_tf = os.path.join(source_dir, 'windows.tf')
    
    if not os.path.exists(windows_tf):
        return ""
    
    with open(windows_tf, 'r') as f:
        content = f.read()
    
    # Replace ip_range placeholder
    content = content.replace('{{ip_range}}', ip_range)
    
    return content


def _process_template_files(template_dir: str, output_dir: str, replacements: Dict[str, str]):
    """Process all template files from the GOAD template directory."""
    for pattern in ['*.tf', '*.tpl']:
        for src_file in glob.glob(os.path.join(template_dir, pattern)):
            filename = os.path.basename(src_file)
            
            with open(src_file, 'r') as f:
                content = f.read()
            
            # Apply replacements
            for placeholder, value in replacements.items():
                content = content.replace(placeholder, value)
            
            # Write to output
            dst_file = os.path.join(output_dir, filename)
            with open(dst_file, 'w') as f:
                f.write(content)


def _process_lab_specific_files(source_dir: str, output_dir: str, replacements: Dict[str, str]):
    """Process lab-specific files that may override templates."""
    for pattern in ['*.tf', '*.tpl']:
        for src_file in glob.glob(os.path.join(source_dir, pattern)):
            filename = os.path.basename(src_file)
            
            # Skip windows.tf as it's handled separately
            if filename == 'windows.tf':
                continue
            
            with open(src_file, 'r') as f:
                content = f.read()
            
            # Apply replacements
            for placeholder, value in replacements.items():
                content = content.replace(placeholder, value)
            
            # Write to output (may override template file)
            dst_file = os.path.join(output_dir, filename)
            with open(dst_file, 'w') as f:
                f.write(content)


def _create_helper_files(output_dir: str, lab_type: str, config: Dict, ip_range: str):
    """Create additional helper files for the GOAD deployment."""
    
    # Create lab info file
    lab_info = {
        'lab_type': lab_type,
        'lab_identifier': config['lab_identifier'],
        'vm_count': config['vm_count'],
        'domains': config['domains'],
        'forests': config['forests'],
        'ip_range': ip_range,
        'description': config['description'],
    }
    
    info_file = os.path.join(output_dir, 'lab_info.json')
    with open(info_file, 'w') as f:
        json.dump(lab_info, f, indent=2)


def extract_vm_info(lab_type: str, base_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract VM information from a GOAD lab's config.json.
    
    Returns dict with:
        - hosts: List of VM info (hostname, role, domain, ip)
        - domains: List of domain info
        - credentials: Default credentials
    """
    if lab_type not in GOAD_LABS:
        raise ValueError(f"Unknown GOAD lab type: {lab_type}")
    
    config = GOAD_LABS[lab_type]
    base_path = base_path or os.getcwd()
    config_file = os.path.join(base_path, config['config_file'])
    
    if not os.path.exists(config_file):
        return {'hosts': [], 'domains': [], 'credentials': {}}
    
    with open(config_file, 'r') as f:
        data = json.load(f)
    
    lab_data = data.get('lab', {})
    hosts_data = lab_data.get('hosts', {})
    domains_data = lab_data.get('domains', {})
    
    # Extract host info
    hosts = []
    for host_id, host_info in hosts_data.items():
        hosts.append({
            'id': host_id,
            'hostname': host_info.get('hostname', host_id),
            'type': host_info.get('type', 'server'),
            'domain': host_info.get('domain', ''),
            'local_admin_password': host_info.get('local_admin_password', ''),
        })
    
    # Extract domain info
    domains = []
    credentials = {}
    for domain_name, domain_info in domains_data.items():
        domains.append({
            'name': domain_name,
            'dc': domain_info.get('dc', ''),
            'netbios': domain_info.get('netbios_name', ''),
        })
        
        # Extract user credentials
        users = domain_info.get('users', {})
        for username, user_info in users.items():
            credentials[f"{domain_info.get('netbios_name', '')}\\{username}"] = {
                'username': username,
                'password': user_info.get('password', ''),
                'domain': domain_name,
                'description': user_info.get('description', ''),
            }
    
    return {
        'hosts': hosts,
        'domains': domains,
        'credentials': credentials,
    }


# =============================================================================
# CLI Interface (for testing)
# =============================================================================

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Process GOAD templates')
    parser.add_argument('lab_type', choices=list(GOAD_LABS.keys()), help='GOAD lab type')
    parser.add_argument('--region', default='us-east-1', help='AWS region')
    parser.add_argument('--zone', default='us-east-1a', help='AWS availability zone')
    parser.add_argument('--ip-range', default=None, help='IP range (e.g., 192.168.56)')
    parser.add_argument('--output', default=None, help='Output directory')
    parser.add_argument('--base-path', default=None, help='Base project path')
    
    args = parser.parse_args()
    
    output_dir = process_goad_templates(
        lab_type=args.lab_type,
        aws_region=args.region,
        aws_zone=args.zone,
        ip_range=args.ip_range,
        output_dir=args.output,
        base_path=args.base_path
    )
    
    print(f"Generated GOAD Terraform files in: {output_dir}")
    print(f"Lab: {args.lab_type}")
    print(f"Region: {args.region}")
    print(f"Zone: {args.zone}")

