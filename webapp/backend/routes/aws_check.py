"""
AWS Check API Routes
Handle AWS credentials and permissions checking
"""

from flask import Blueprint, jsonify, request
from pathlib import Path
import sys
import subprocess
import json

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.services.aws_permissions_service import AWSPermissionsService
from webapp.backend.utils.config_parser import ConfigParser

bp = Blueprint('aws_check', __name__)

# Module-level cache for Route 53 zones response (refreshed per page lifetime
# on the frontend; backend caches for a short TTL to avoid hammering the API).
_ROUTE53_ZONES_CACHE = {"data": None, "ts": 0.0}
_ROUTE53_ZONES_TTL_S = 30.0


def _scan_tfvars_for_domains():
    """Walk configs/*.tfvars and build a map of domain -> project_name.

    Looks at the primary_domain_name and backup_domains fields. The project
    name is the tfvars filename stem (e.g. ``configs/c2_adhoc_dev_*.tfvars``
    -> ``c2_adhoc_dev_*``). The legacy global ``terraform.tfvars`` is keyed
    by its own ``project_name`` field if present.
    """
    domain_to_project = {}
    config_dir = project_root / "configs"
    if not config_dir.exists():
        return domain_to_project
    for tfv in config_dir.glob("*.tfvars"):
        # Skip example/template files
        name = tfv.name.lower()
        if name.endswith(".example") or "example" in name:
            continue
        try:
            cfg = ConfigParser.parse_tfvars(tfv)
        except Exception:
            continue
        if not cfg:
            continue
        if tfv.name == "terraform.tfvars":
            project = (cfg.get("project_name") or "terraform.tfvars").strip() or "terraform.tfvars"
        else:
            project = tfv.stem
        primary = (cfg.get("primary_domain_name") or "").strip().rstrip(".")
        if primary:
            domain_to_project.setdefault(primary.lower(), project)
        backups = cfg.get("backup_domains") or []
        if isinstance(backups, list):
            for b in backups:
                b = (b or "").strip().rstrip(".").lower()
                if b:
                    domain_to_project.setdefault(b, project)
    return domain_to_project


@bp.route('/route53/zones', methods=['GET'])
def list_route53_zones():
    """List Route 53 hosted zones in this account, annotated with project use.

    Response shape::

        {
          "success": true,
          "zones": [
            {
              "name": "example.com",
              "id": "Z3AQBSTGFYJSTF",
              "private": false,
              "record_count": 4,
              "in_use_by_project_or_null": "c2_adhoc_dev_..." | null
            }, ...
          ]
        }

    Pass ``?refresh=1`` to bust the short-lived backend cache.
    """
    try:
        import time
        import boto3

        refresh = (request.args.get('refresh') or '').lower() in ('1', 'true', 'yes')
        now = time.time()
        cached = _ROUTE53_ZONES_CACHE.get("data")
        if cached and not refresh and (now - _ROUTE53_ZONES_CACHE.get("ts", 0.0)) < _ROUTE53_ZONES_TTL_S:
            return jsonify(cached)

        # Walk configs/*.tfvars once per request to find what's in use.
        domain_in_use = _scan_tfvars_for_domains()

        zones = []
        try:
            r53 = boto3.client('route53')
            paginator = r53.get_paginator('list_hosted_zones')
            for page in paginator.paginate():
                for z in page.get('HostedZones', []):
                    raw = z.get('Name', '')
                    name = raw.rstrip('.').lower()
                    is_private = bool(z.get('Config', {}).get('PrivateZone', False))
                    zones.append({
                        "name": name,
                        "id": z.get('Id', '').split('/')[-1],
                        "private": is_private,
                        "record_count": z.get('ResourceRecordSetCount', 0),
                        "in_use_by_project_or_null": domain_in_use.get(name),
                    })
        except Exception as inner:
            # Surface the AWS error but return success=false so the frontend
            # can fall back to a plain text-input gracefully.
            return jsonify({
                "success": False,
                "zones": [],
                "error": f"Route 53 list_hosted_zones failed: {inner}",
            })

        payload = {
            "success": True,
            "zones": zones,
        }
        _ROUTE53_ZONES_CACHE["data"] = payload
        _ROUTE53_ZONES_CACHE["ts"] = now
        return jsonify(payload)
    except Exception as e:
        return jsonify({
            "success": False,
            "zones": [],
            "error": str(e),
        }), 500

@bp.route('/credentials', methods=['GET'])
def check_credentials():
    """Check current AWS CLI credentials"""
    try:
        # Run AWS CLI command to get caller identity
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            try:
                identity = json.loads(result.stdout)
                return jsonify({
                    "success": True,
                    "authenticated": True,
                    "account": identity.get("Account", ""),
                    "user": identity.get("Arn", ""),
                    "user_id": identity.get("UserId", ""),
                    "message": "AWS credentials are valid"
                })
            except json.JSONDecodeError:
                return jsonify({
                    "success": True,
                    "authenticated": True,
                    "raw_output": result.stdout,
                    "message": "AWS credentials are valid"
                })
        else:
            # Check if AWS CLI is installed
            if "aws: command not found" in result.stderr or "aws: not found" in result.stderr:
                return jsonify({
                    "success": False,
                    "authenticated": False,
                    "error": "AWS CLI is not installed",
                    "message": "Please install AWS CLI to use this feature"
                }), 400
            
            # Credentials are invalid or not configured
            return jsonify({
                "success": False,
                "authenticated": False,
                "error": result.stderr.strip() or "AWS credentials not configured or invalid",
                "message": "AWS credentials are not configured or invalid. Please run 'aws configure' to set up your credentials."
            }), 401
            
    except FileNotFoundError:
        return jsonify({
            "success": False,
            "authenticated": False,
            "error": "AWS CLI not found",
            "message": "AWS CLI is not installed. Please install it first."
        }), 500
    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "authenticated": False,
            "error": "Command timed out",
            "message": "AWS credentials check timed out"
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "authenticated": False,
            "error": str(e),
            "message": f"Error checking credentials: {str(e)}"
        }), 500

@bp.route('/ssh-key', methods=['GET'])
def check_ssh_key():
    """Check if the user has an SSH key pair for EC2 access"""
    import os
    home = Path.home()

    # Check common SSH key locations
    key_checks = [
        ('id_ed25519', home / '.ssh' / 'id_ed25519', home / '.ssh' / 'id_ed25519.pub'),
        ('id_rsa', home / '.ssh' / 'id_rsa', home / '.ssh' / 'id_rsa.pub'),
    ]

    found_keys = []
    for name, priv, pub in key_checks:
        if priv.exists() and pub.exists():
            # Read public key to show fingerprint
            try:
                result = subprocess.run(
                    ['ssh-keygen', '-l', '-f', str(pub)],
                    capture_output=True, text=True, timeout=5
                )
                fingerprint = result.stdout.strip() if result.returncode == 0 else ''
            except Exception:
                fingerprint = ''

            found_keys.append({
                'name': name,
                'private_key': str(priv),
                'public_key': str(pub),
                'fingerprint': fingerprint,
            })

    if found_keys:
        # Prefer ed25519 over RSA
        best = found_keys[0]
        return jsonify({
            'success': True,
            'has_key': True,
            'key_type': best['name'],
            'private_key_path': best['private_key'],
            'public_key_path': best['public_key'],
            'fingerprint': best['fingerprint'],
            'all_keys': found_keys,
            'message': f"SSH key found: {best['name']} ({best['fingerprint']})",
            'note': 'This key will be uploaded to AWS during deployment for bastion/jumpbox SSH access. '
                     'It is also used for the CS REST API SSH tunnel and GOAD AD provisioning.'
        })
    else:
        return jsonify({
            'success': True,
            'has_key': False,
            'message': 'No SSH key pair found in ~/.ssh/',
            'fix': 'Generate one with: ssh-keygen -t ed25519 -C "red-team-infra"',
            'note': 'An SSH key pair is required for EC2 instance access. '
                     'The public key is uploaded to AWS, the private key stays on your machine.'
        })


@bp.route('/github-cli', methods=['GET'])
def check_github_cli():
    """Check if user is logged into GitHub CLI and has access to the tools repo.

    2026-05-28 — Real-pipeline audit fix (HIGH #13): the tools repo
    used to be hard-coded to `harr-sudo/red-team-tools` so every
    operator other than the project author saw a permanent red-X in
    Settings even though the tools repo is OPTIONAL (only consulted
    when `tools_repo_https_token` is set in tfvars). Resolution order:
      1. `?repo=owner/name` query arg (operator override).
      2. `TOOLS_REPO` env var on the dashboard server.
      3. Skip the repo-access probe entirely — just report `gh auth`
         status. Authenticating with GitHub is itself optional, and a
         hard-coded probe against someone else's private repo is worse
         signal than no probe at all.
    """
    import os as _os
    import re

    TOOLS_REPO = (request.args.get("repo")
                  or _os.environ.get("TOOLS_REPO")
                  or "").strip()
    TOOLS_REPO_URL = f"https://github.com/{TOOLS_REPO}" if TOOLS_REPO else ""
    
    try:
        # Run gh auth status to check if logged in
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            # Parse the output to extract user info
            output = result.stdout + result.stderr  # gh auth status outputs to stderr
            
            # Try to extract username from output
            username = None
            account_type = None
            
            # Look for "Logged in to github.com account <username>"
            match = re.search(r'Logged in to github\.com account (\S+)', output)
            if match:
                username = match.group(1)
            
            # Check if it's a token or SSH auth
            if 'Token:' in output:
                account_type = 'token'
            elif 'ssh' in output.lower():
                account_type = 'ssh'
            
            # No configured tools repo → just return gh-auth status as
            # success; skip the repo-access probe entirely. Operator can
            # set TOOLS_REPO=<owner/name> env on the dashboard server
            # or pass ?repo=... if they actually use a private repo.
            if not TOOLS_REPO:
                return jsonify({
                    "success": True,
                    "authenticated": True,
                    "has_repo_access": None,  # not probed
                    "username": username,
                    "account_type": account_type,
                    "message": ("GitHub CLI authenticated. No tools repo "
                                "configured (set TOOLS_REPO env var or "
                                "?repo= to enable a private-repo probe)."),
                })

            # Now check if user has access to the configured tools repo
            repo_access_result = subprocess.run(
                ["gh", "repo", "view", TOOLS_REPO, "--json", "name,visibility"],
                capture_output=True,
                text=True,
                timeout=15
            )
            
            if repo_access_result.returncode == 0:
                # User has access to the repo
                try:
                    repo_info = json.loads(repo_access_result.stdout)
                    return jsonify({
                        "success": True,
                        "authenticated": True,
                        "has_repo_access": True,
                        "username": username,
                        "account_type": account_type,
                        "repo_name": repo_info.get("name", TOOLS_REPO),
                        "repo_visibility": repo_info.get("visibility", "unknown"),
                        "message": "GitHub CLI authenticated with tools repo access",
                        "tools_repo": TOOLS_REPO_URL
                    })
                except json.JSONDecodeError:
                    return jsonify({
                        "success": True,
                        "authenticated": True,
                        "has_repo_access": True,
                        "username": username,
                        "account_type": account_type,
                        "message": "GitHub CLI authenticated with tools repo access",
                        "tools_repo": TOOLS_REPO_URL
                    })
            else:
                # User is logged in but doesn't have access to the repo
                repo_error = repo_access_result.stderr.strip()
                
                return jsonify({
                    "success": True,
                    "authenticated": True,
                    "has_repo_access": False,
                    "username": username,
                    "account_type": account_type,
                    "message": "GitHub CLI authenticated but no access to tools repository",
                    "repo_error": repo_error,
                    "tools_repo": TOOLS_REPO_URL,
                    "access_request_info": {
                        "contact": "Harris",
                        "repo": TOOLS_REPO,
                        "instruction": f"Please ask Harris to grant you access to {TOOLS_REPO_URL}"
                    }
                })
        else:
            error_output = result.stderr.strip() or result.stdout.strip()
            
            # Check if gh CLI is installed but not logged in
            if "not logged" in error_output.lower() or "authentication" in error_output.lower():
                return jsonify({
                    "success": False,
                    "authenticated": False,
                    "has_repo_access": False,
                    "error": "Not logged in to GitHub CLI",
                    "message": "Please run 'gh auth login' to authenticate with GitHub CLI",
                    "tools_repo": TOOLS_REPO_URL
                }), 401
            
            return jsonify({
                "success": False,
                "authenticated": False,
                "has_repo_access": False,
                "error": error_output or "GitHub CLI authentication failed",
                "message": "GitHub CLI authentication check failed. Please run 'gh auth login'.",
                "tools_repo": TOOLS_REPO_URL
            }), 401
            
    except FileNotFoundError:
        return jsonify({
            "success": False,
            "authenticated": False,
            "has_repo_access": False,
            "error": "GitHub CLI (gh) not found",
            "message": "GitHub CLI is not installed. Please install it from https://cli.github.com/",
            "tools_repo": TOOLS_REPO_URL
        }), 500
    except subprocess.TimeoutExpired:
        return jsonify({
            "success": False,
            "authenticated": False,
            "has_repo_access": False,
            "error": "Command timed out",
            "message": "GitHub CLI check timed out"
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "authenticated": False,
            "has_repo_access": False,
            "error": str(e),
            "message": f"Error checking GitHub CLI: {str(e)}"
        }), 500

@bp.route('/check-domain', methods=['POST'])
def check_domain_availability():
    """Check if subdomains already have DNS records in Route53.

    Prevents operators from accidentally overwriting records from another deployment.
    """
    data = request.get_json() or {}
    domain = data.get('domain', '')
    subdomains = data.get('subdomains', [])
    region = data.get('region', 'us-east-1')

    if not domain or not subdomains:
        return jsonify({'success': False, 'error': 'domain and subdomains required'}), 400

    try:
        # Get the hosted zone ID for this domain
        result = subprocess.run(
            ['aws', 'route53', 'list-hosted-zones-by-name',
             '--dns-name', domain, '--max-items', '1', '--output', 'json'],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return jsonify({'success': False, 'error': f'Route53 query failed: {result.stderr}'}), 500

        zones = json.loads(result.stdout).get('HostedZones', [])
        zone_id = None
        for z in zones:
            # Match exact domain (Route53 adds trailing dot)
            if z['Name'].rstrip('.') == domain.rstrip('.'):
                zone_id = z['Id'].split('/')[-1]
                break

        if not zone_id:
            return jsonify({
                'success': True,
                'zone_found': False,
                'message': f'No Route53 hosted zone found for {domain}. '
                           'Zone will be created during deployment.',
                'results': []
            })

        # Check each subdomain for existing records
        results = []
        for sub in subdomains:
            fqdn = f"{sub}.{domain}"
            rec_result = subprocess.run(
                ['aws', 'route53', 'list-resource-record-sets',
                 '--hosted-zone-id', zone_id,
                 '--query', f"ResourceRecordSets[?Name=='{fqdn}.']",
                 '--output', 'json'],
                capture_output=True, text=True, timeout=15
            )

            records = []
            if rec_result.returncode == 0:
                try:
                    records = json.loads(rec_result.stdout) or []
                except json.JSONDecodeError:
                    records = []

            if records:
                # Extract record details
                rec_info = []
                for r in records:
                    rtype = r.get('Type', '?')
                    values = [rv.get('Value', '') for rv in r.get('ResourceRecords', [])]
                    alias = r.get('AliasTarget', {}).get('DNSName', '')
                    rec_info.append({
                        'type': rtype,
                        'values': values if values else [alias] if alias else ['(alias)'],
                    })
                results.append({
                    'subdomain': sub,
                    'fqdn': fqdn,
                    'available': False,
                    'records': rec_info,
                })
            else:
                results.append({
                    'subdomain': sub,
                    'fqdn': fqdn,
                    'available': True,
                    'records': [],
                })

        has_conflict = any(not r['available'] for r in results)

        return jsonify({
            'success': True,
            'zone_found': True,
            'zone_id': zone_id,
            'domain': domain,
            'has_conflict': has_conflict,
            'results': results,
            'message': 'One or more subdomains already have DNS records — deploying will overwrite them.' if has_conflict else 'All subdomains are available.',
        })

    except subprocess.TimeoutExpired:
        return jsonify({'success': False, 'error': 'Route53 query timed out'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bp.route('/permissions', methods=['GET'])
def check_permissions():
    """Check if AWS credentials have sufficient permissions for deployment"""
    try:
        # First verify AWS connectivity
        result = subprocess.run(
            ["aws", "sts", "get-caller-identity"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            return jsonify({
                "success": False,
                "error": "AWS credentials not configured or invalid",
                "message": "Please configure AWS credentials first using 'aws configure'"
            }), 401
        
        # Try policy simulation first (more accurate)
        simulation_result = AWSPermissionsService.check_using_policy_simulation()
        
        if simulation_result.get("success"):
            # Policy simulation succeeded
            missing = simulation_result.get("missing_permissions", [])
            available = simulation_result.get("available_permissions", [])
            overall = simulation_result.get("overall", "unknown")
            
            # Determine status
            if overall == "complete":
                status = "sufficient"
                status_icon = "✅"
                status_text = "All required permissions are available"
            elif overall == "partial":
                status = "partial"
                status_icon = "⚠️"
                status_text = f"Some permissions are missing ({len(missing)} missing, {len(available)} available)"
            else:
                status = "insufficient"
                status_icon = "❌"
                status_text = "Many required permissions are missing"
            
            return jsonify({
                "success": True,
                "method": "policy_simulation",
                "status": status,
                "status_icon": status_icon,
                "status_text": status_text,
                "overall": overall,
                "missing_permissions": missing,
                "available_permissions": available,
                "total_required": len(missing) + len(available),
                "total_available": len(available),
                "total_missing": len(missing),
                "permissions": simulation_result.get("permissions", {})
            })
        else:
            # Fallback to simple checks
            batch_result = AWSPermissionsService.check_permissions_batch()
            missing = batch_result.get("missing_permissions", [])
            available = batch_result.get("available_permissions", [])
            overall = batch_result.get("overall", "unknown")
            
            # Determine status
            if overall == "complete":
                status = "sufficient"
                status_icon = "✅"
                status_text = "All testable permissions are available"
            elif overall == "partial":
                status = "partial"
                status_icon = "⚠️"
                status_text = f"Some permissions may be missing (best-effort check)"
            else:
                status = "unknown"
                status_icon = "⚠️"
                status_text = "Cannot fully verify permissions (write permissions cannot be safely tested)"
            
            return jsonify({
                "success": True,
                "method": "simple_check",
                "status": status,
                "status_icon": status_icon,
                "status_text": status_text,
                "overall": overall,
                "missing_permissions": missing,
                "available_permissions": available,
                "total_required": len(missing) + len(available),
                "total_available": len(available),
                "total_missing": len(missing),
                "categories": batch_result.get("categories", {}),
                "warning": simulation_result.get("error", "Using simplified permission checks (write permissions cannot be safely tested)")
            })
            
    except FileNotFoundError:
        return jsonify({
            "success": False,
            "error": "AWS CLI not found",
            "message": "AWS CLI is not installed. Please install it first."
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "message": f"Error checking permissions: {str(e)}"
        }), 500

