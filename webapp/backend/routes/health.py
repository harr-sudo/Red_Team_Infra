
from flask import Blueprint, jsonify
from pathlib import Path
import json
import os
import sys
import subprocess
import shutil

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from webapp.backend.utils.config_parser import ConfigParser
from webapp.backend.utils.validators import ConfigValidator

bp = Blueprint('health', __name__)

# Paths
config_dir = project_root / "configs"
tfvars_file = config_dir / "terraform.tfvars"
UPLOAD_FOLDER = project_root / "uploads"
ALLOWED_EXTENSIONS = {'tar', 'gz', 'zip', 'tar.gz'}

def allowed_file(filename):
    """Check if file extension is allowed"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS or \
           filename.endswith('.tar.gz')


@bp.route('/terraform', methods=['GET'])
def check_terraform():
    """Check if Terraform CLI is installed"""
    try:
        # Check if terraform is in PATH
        terraform_path = shutil.which('terraform')
        
        if not terraform_path:
            return jsonify({
                "success": True,
                "installed": False,
                "error": "Terraform CLI not found in PATH. Please install Terraform."
            })
        
        # Get version
        result = subprocess.run(
            ['terraform', 'version', '-json'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        version = "Unknown"
        if result.returncode == 0:
            try:
                import json
                version_data = json.loads(result.stdout)
                version = version_data.get('terraform_version', 'Unknown')
            except:
                # Fallback to parsing text output
                result_text = subprocess.run(
                    ['terraform', 'version'],
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                if result_text.returncode == 0:
                    first_line = result_text.stdout.strip().split('\n')[0]
                    version = first_line.replace('Terraform v', '').strip()
        
        return jsonify({
            "success": True,
            "installed": True,
            "version": version,
            "path": terraform_path
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({
            "success": True,
            "installed": False,
            "error": "Terraform command timed out"
        })
    except FileNotFoundError:
        return jsonify({
            "success": True,
            "installed": False,
            "error": "Terraform CLI not found. Please install Terraform."
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "installed": False,
            "error": str(e)
        }), 500


@bp.route('/aws-cli', methods=['GET'])
def check_aws_cli():
    """Check if AWS CLI is installed"""
    try:
        # Check if aws is in PATH
        aws_path = shutil.which('aws')
        
        if not aws_path:
            return jsonify({
                "success": True,
                "installed": False,
                "error": "AWS CLI not found in PATH. Please install AWS CLI."
            })
        
        # Get version
        result = subprocess.run(
            ['aws', '--version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        version = "Unknown"
        if result.returncode == 0:
            # Output format: aws-cli/2.x.x Python/3.x.x ...
            version_line = result.stdout.strip() or result.stderr.strip()
            if version_line:
                parts = version_line.split()
                if parts:
                    version = parts[0].replace('aws-cli/', '')
        
        return jsonify({
            "success": True,
            "installed": True,
            "version": version,
            "path": aws_path
        })
        
    except subprocess.TimeoutExpired:
        return jsonify({
            "success": True,
            "installed": False,
            "error": "AWS CLI command timed out"
        })
    except FileNotFoundError:
        return jsonify({
            "success": True,
            "installed": False,
            "error": "AWS CLI not found. Please install AWS CLI."
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "installed": False,
            "error": str(e)
        }), 500

@bp.route('/domain-config', methods=['GET'])
def check_domain_config():
    """Check if domain is configured"""
    try:
        if not tfvars_file.exists():
            return jsonify({
                "success": True,
                "configured": False,
                "error": "Configuration file not found"
            })
            
        config = ConfigParser.parse_tfvars(tfvars_file)
        primary_domain = config.get('primary_domain_name', '').strip()
        
        if not primary_domain:
            return jsonify({
                "success": True,
                "configured": False,
                "error": "Primary domain not configured"
            })
            
        # Validate domain config
        is_valid, errors = ConfigValidator.validate_domain_config(config)
        
        return jsonify({
            "success": True,
            "configured": is_valid,
            "domain_info": {
                "primary_domain": primary_domain,
                "c2_subdomain": config.get('c2_subdomain', 'api'),
                "www_subdomain": config.get('www_subdomain', 'www'),
                "cdn_subdomain": config.get('cdn_subdomain', 'cdn'),
                "backup_domains": config.get('backup_domains', [])
            },
            "errors": errors
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@bp.route('/route53-domains', methods=['GET'])
def list_route53_domains():
    """List Route 53 registered domains AND hosted zones in the user's AWS account.

    Returns both shapes for backward compatibility:
      - ``domains``: registered domains (Route 53 Domains API, us-east-1 only).
      - ``zones``: hosted zones (Route 53 global API) — used by the Domains &
        DNS Settings card, with ``record_count`` + ``private`` + ``in_use_by``
        derived from the currently selected deployment's primary domain.
    """
    try:
        import boto3
        # Route 53 Domains API is only available in us-east-1
        domains_client = boto3.client('route53domains', region_name='us-east-1')
        domains = []
        try:
            paginator = domains_client.get_paginator('list_domains')
            for page in paginator.paginate():
                for d in page.get('Domains', []):
                    domains.append({
                        "domain_name": d['DomainName'],
                        "auto_renew": d.get('AutoRenew', False),
                        "expiry": d.get('Expiry', '').isoformat() if hasattr(d.get('Expiry', ''), 'isoformat') else str(d.get('Expiry', '')),
                        "transfer_lock": d.get('TransferLock', False)
                    })
        except Exception as inner:
            # Registered-domains API may be unauthorized in some accounts; do
            # not fail the whole response — hosted zones are independent.
            print(f"list_route53_domains: registered domains lookup failed: {inner}")

        # Hosted zones — global API. Used by the Domains & DNS Settings card.
        zones = []
        try:
            route53 = boto3.client('route53')
            zones_paginator = route53.get_paginator('list_hosted_zones')
            # Best-effort: detect the currently selected deployment's primary
            # domain so we can flag the in-use zone. Failure is non-fatal.
            in_use_domain = None
            try:
                config = ConfigParser.parse_tfvars(str(tfvars_file)) if tfvars_file.exists() else {}
                in_use_domain = (config.get('primary_domain_name') or '').strip().rstrip('.')
            except Exception:
                pass

            for page in zones_paginator.paginate():
                for z in page.get('HostedZones', []):
                    raw_name = z.get('Name', '')
                    name = raw_name.rstrip('.')
                    is_private = bool(z.get('Config', {}).get('PrivateZone', False))
                    zones.append({
                        "name": name,
                        "id": z.get('Id', '').split('/')[-1],
                        "record_count": z.get('ResourceRecordSetCount', 0),
                        "private": is_private,
                        "in_use_by": "current deployment" if in_use_domain and in_use_domain == name else None,
                    })
        except Exception as inner:
            print(f"list_route53_domains: hosted-zones lookup failed: {inner}")

        return jsonify({
            "success": True,
            "domains": domains,
            "zones": zones,
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "domains": [],
            "zones": [],
            "error": str(e)
        })

@bp.route('/secrets', methods=['GET'])
def list_secrets():
    """List Secrets Manager secrets relevant to the project.

    Returns names + LastChangedDate / LastAccessedDate only — never secret
    values. Filtered to known patterns:
      - ``cs-license-key``                 (Cobalt Strike license)
      - ``*-github-token``                 (per-deployment tools-repo PAT)
      - ``*-cs-team-server-password``      (team-server bootstrap password)
      - ``*-bastion-admin-password``       (bastion RDP admin password)
    """
    try:
        import os
        import boto3
        region = os.environ.get('AWS_REGION') or os.environ.get('AWS_DEFAULT_REGION') or 'eu-central-1'
        client = boto3.client('secretsmanager', region_name=region)

        def is_project_secret(name: str) -> bool:
            if name == 'cs-license-key':
                return True
            if name.endswith('-github-token'):
                return True
            if name.endswith('-cs-team-server-password'):
                return True
            if name.endswith('-bastion-admin-password'):
                return True
            return False

        out = []
        paginator = client.get_paginator('list_secrets')
        for page in paginator.paginate():
            for s in page.get('SecretList', []):
                name = s.get('Name', '')
                if not is_project_secret(name):
                    continue
                last_changed = s.get('LastChangedDate')
                last_accessed = s.get('LastAccessedDate')
                out.append({
                    'name': name,
                    'description': s.get('Description', '') or '',
                    'last_changed': last_changed.isoformat() if hasattr(last_changed, 'isoformat') else None,
                    'last_accessed': last_accessed.isoformat() if hasattr(last_accessed, 'isoformat') else None,
                    'arn': s.get('ARN', ''),
                })

        # Sort: cs-license-key first, then alphabetical
        out.sort(key=lambda r: (0 if r['name'] == 'cs-license-key' else 1, r['name']))

        return jsonify({
            'success': True,
            'secrets': out,
            'region': region,
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e),
            'secrets': [],
        }), 200

@bp.route('/bootstrap-status', methods=['GET'])
def check_bootstrap_status():
    """Check if EC2 instance bootstrap scripts have completed via S3 status files"""
    try:
        import boto3
        from flask import request as req

        bucket = req.args.get('bucket')
        region = req.args.get('region', 'eu-central-1')

        if not bucket:
            return jsonify({"success": False, "error": "bucket parameter required"})

        s3 = boto3.client('s3', region_name=region)
        response = s3.list_objects_v2(Bucket=bucket, Prefix='status/')

        instances = {}
        for obj in response.get('Contents', []):
            key = obj['Key']
            try:
                body = s3.get_object(Bucket=bucket, Key=key)['Body'].read().decode('utf-8')
                data = json.loads(body)
                instance_id = data.get('instance_id', key)
                instances[instance_id] = {
                    "role": data.get('role', 'unknown'),
                    "status": data.get('status', 'unknown'),
                    "timestamp": data.get('timestamp', ''),
                }
            except Exception:
                pass

        all_complete = all(i['status'] == 'complete' for i in instances.values()) if instances else False

        return jsonify({
            "success": True,
            "instances": instances,
            "all_complete": all_complete,
            "total": len(instances)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@bp.route('/system-deps', methods=['GET'])
def check_system_deps():
    """Check all system dependencies required by the webapp"""
    deps = [
        ('terraform', 'terraform', True, 'brew install terraform'),
        ('aws', 'aws', True, 'brew install awscli'),
        ('python3', 'python3', True, 'brew install python3'),
        ('ssh', 'ssh', True, 'Built into macOS/Linux'),
        ('jq', 'jq', True, 'brew install jq'),
        ('gh', 'gh', False, 'brew install gh'),
        ('ansible', 'ansible', False, 'pip install ansible'),
    ]

    # Python packages (checked via import, not shutil.which)
    python_pkgs = [
        ('boto3', 'boto3', True, 'pip install boto3'),
    ]

    results = []
    for name, cmd, required, install in deps:
        found = shutil.which(cmd) is not None
        version = None
        if found:
            try:
                if name == 'terraform':
                    r = subprocess.run([cmd, 'version', '-json'], capture_output=True, text=True, timeout=5)
                    v = json.loads(r.stdout) if r.returncode == 0 else {}
                    version = v.get('terraform_version', '')
                elif name == 'aws':
                    r = subprocess.run([cmd, '--version'], capture_output=True, text=True, timeout=5)
                    version = r.stdout.strip().split()[0].replace('aws-cli/', '') if r.returncode == 0 else ''
                elif name == 'python3':
                    r = subprocess.run([cmd, '--version'], capture_output=True, text=True, timeout=5)
                    version = r.stdout.strip().replace('Python ', '') if r.returncode == 0 else ''
                elif name == 'ansible':
                    r = subprocess.run([cmd, '--version'], capture_output=True, text=True, timeout=5)
                    version = r.stdout.split('\n')[0].split()[-1].strip('[]') if r.returncode == 0 else ''
                elif name == 'gh':
                    r = subprocess.run([cmd, '--version'], capture_output=True, text=True, timeout=5)
                    version = r.stdout.strip().split()[2] if r.returncode == 0 else ''
                elif name == 'jq':
                    r = subprocess.run([cmd, '--version'], capture_output=True, text=True, timeout=5)
                    version = r.stdout.strip().replace('jq-', '') if r.returncode == 0 else ''
            except Exception:
                pass

        results.append({
            'name': name,
            'installed': found,
            'required': required,
            'version': version,
            'install_cmd': install
        })

    # Check Python packages
    for name, pkg, required, install in python_pkgs:
        found = False
        version = None
        try:
            mod = __import__(pkg)
            found = True
            version = getattr(mod, '__version__', 'installed')
        except ImportError:
            pass
        results.append({
            'name': name,
            'installed': found,
            'required': required,
            'version': version,
            'install_cmd': install
        })

    return jsonify({'success': True, 'deps': results})


@bp.route('/agent', methods=['GET'])
def check_agent():
    """Surface ANTHROPIC_API_KEY + anthropic SDK presence for the bolt-on agentic fallback.

    Operators need to know BEFORE a job goes STUCK whether the agent
    fallback path is usable. The actual API key is NEVER returned — we
    only report presence ("configured": bool) and where the key came
    from ("env" today; "secrets-manager" reserved for a future lookup
    path; "none" when unset).

    See ``webapp/backend/services/bolton_agent_service.py`` which reads
    the same env vars on invocation, and
    ``docs/internal/VULNERABLE_LAB_BOLTON_PLAN.md`` §7.9 for the
    end-to-end operator configuration story.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    configured = bool(api_key)
    key_source = "env" if api_key else "none"

    # Default mirrors bolton_agent_service.DEFAULT_MODEL — we read the
    # env var directly here so this endpoint stays cheap (no import of
    # the agent service, which pulls in audit + lazy-imports).
    model = os.environ.get("BOLTON_AGENT_MODEL", "claude-sonnet-4-6")

    try:
        import anthropic  # noqa: F401
        anthropic_sdk_installed = True
    except ImportError:
        anthropic_sdk_installed = False

    return jsonify({
        "success": True,
        "configured": configured,
        "model": model,
        "key_source": key_source,
        "anthropic_sdk_installed": anthropic_sdk_installed,
    })


@bp.route('/cobalt-strike-file', methods=['GET'])
def check_cobalt_strike_file():
    """Check if Cobalt Strike file is uploaded"""
    try:
        if not UPLOAD_FOLDER.exists():
            return jsonify({
                "success": True,
                "has_file": False
            })
            
        files = list(UPLOAD_FOLDER.glob("*"))
        cobalt_strike_files = [
            f for f in files 
            if f.is_file() and allowed_file(f.name)
        ]
        
        return jsonify({
            "success": True,
            "has_file": len(cobalt_strike_files) > 0
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

