"""
Cost Service
============
AWS Cost Explorer integration + real-time running cost estimates.
Provides per-project cost breakdowns, budget tracking, and caching.
"""

import json
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import boto3
from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError

# ---------------------------------------------------------------------------
# Pricing data — eu-central-1 on-demand hourly rates (USD)
# ---------------------------------------------------------------------------
EC2_HOURLY_RATES = {
    "t3.nano": 0.0058, "t3.micro": 0.0116, "t3.small": 0.0232,
    "t3.medium": 0.0464, "t3.large": 0.0928, "t3.xlarge": 0.1856,
    "t2.nano": 0.0067, "t2.micro": 0.0134, "t2.small": 0.0268,
    "t2.medium": 0.0536, "t2.large": 0.1072, "t2.xlarge": 0.2144,
    "m5.large": 0.1150, "m5.xlarge": 0.2300,
}

FIXED_HOURLY = {
    "nat_gateway": 0.052,
    "eip_idle": 0.005,
}

FIXED_MONTHLY = {
    "route53_zone": 0.50,
    "secrets_manager_secret": 0.40,
}

# Hours per month for projection
HOURS_PER_MONTH = 730

DEFAULT_SETTINGS = {
    "budget_threshold": 500,
}

_settings_lock = threading.Lock()


class CostService:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.cache_dir = project_root / "logs" / "cost_cache"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir = project_root / "logs" / "deployment_state"
        self.resources_file = project_root / "logs" / "deployment_resources.json"
        self.settings_file = project_root / "logs" / "cost_settings.json"

    # ------------------------------------------------------------------
    # Settings persistence
    # ------------------------------------------------------------------
    def load_settings(self) -> dict:
        with _settings_lock:
            if self.settings_file.exists():
                try:
                    return json.loads(self.settings_file.read_text())
                except (json.JSONDecodeError, IOError):
                    pass
        return dict(DEFAULT_SETTINGS)

    def save_settings(self, settings: dict):
        merged = dict(DEFAULT_SETTINGS)
        if "budget_threshold" in settings:
            merged["budget_threshold"] = max(0, float(settings["budget_threshold"]))
        with _settings_lock:
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            self.settings_file.write_text(json.dumps(merged, indent=2))
        return merged

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------
    def _cache_path(self, project_name: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name)
        return self.cache_dir / f"{safe}.json"

    def _read_cache(self, project_name: str, ttl_minutes: int) -> Optional[dict]:
        path = self._cache_path(project_name)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            fetched = datetime.fromisoformat(data["fetched_at"])
            age = (datetime.now() - fetched).total_seconds() / 60
            if age <= ttl_minutes:
                data["cache_age_minutes"] = round(age, 1)
                data["cached"] = True
                return data
        except (json.JSONDecodeError, KeyError, ValueError):
            pass
        return None

    def _write_cache(self, project_name: str, data: dict):
        path = self._cache_path(project_name)
        data["fetched_at"] = datetime.now().isoformat()
        path.write_text(json.dumps(data, indent=2, default=str))

    # ------------------------------------------------------------------
    # AWS Cost Explorer — actual billed costs
    # ------------------------------------------------------------------
    def get_aws_costs(self, project_name: str, force_refresh: bool = True, region: Optional[str] = None) -> dict:
        """Query AWS Cost Explorer for costs. Tries tag-filtered first, falls back to total account costs.

        Args:
            project_name: project tag value to filter by.
            force_refresh: ignored here; reserved for cache control by callers.
            region: optional AWS region (e.g. 'eu-central-1'). When provided,
                Cost Explorer's REGION dimension is added to the filter so only
                spend for that region is returned. Confirmed supported per
                https://docs.aws.amazon.com/aws-cost-management/latest/APIReference/API_GetCostAndUsage.html
                (Dimensions key REGION).
        """
        try:
            # Cost Explorer endpoint is global, always us-east-1
            ce = boto3.client("ce", region_name="us-east-1")

            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=30)

            # Build optional region dimension filter (used for both tag and fallback queries)
            region_dim_filter = None
            if region:
                region_dim_filter = {
                    "Dimensions": {"Key": "REGION", "Values": [region]}
                }

            # Try tag-filtered query first
            tag_filtered = True
            try:
                tag_filter = {
                    "Tags": {
                        "Key": "Project",
                        "Values": [project_name],
                    }
                }
                # Combine tag + region with AND when region is specified
                combined_filter = (
                    {"And": [tag_filter, region_dim_filter]}
                    if region_dim_filter else tag_filter
                )
                response = ce.get_cost_and_usage(
                    TimePeriod={
                        "Start": start_date.isoformat(),
                        "End": end_date.isoformat(),
                    },
                    Granularity="DAILY",
                    Filter=combined_filter,
                    GroupBy=[
                        {"Type": "DIMENSION", "Key": "SERVICE"},
                    ],
                    Metrics=["UnblendedCost"],
                )
                # Check if tag filter returned any non-zero data
                has_data = any(
                    float(g["Metrics"]["UnblendedCost"]["Amount"]) > 0.001
                    for r in response.get("ResultsByTime", [])
                    for g in r.get("Groups", [])
                )
                if not has_data:
                    tag_filtered = False
            except Exception:
                tag_filtered = False

            # Fall back to total account costs (no tag filter, but keep region filter if set)
            if not tag_filtered:
                fallback_kwargs = dict(
                    TimePeriod={
                        "Start": start_date.isoformat(),
                        "End": end_date.isoformat(),
                    },
                    Granularity="DAILY",
                    GroupBy=[
                        {"Type": "DIMENSION", "Key": "SERVICE"},
                    ],
                    Metrics=["UnblendedCost"],
                )
                if region_dim_filter:
                    fallback_kwargs["Filter"] = region_dim_filter
                response = ce.get_cost_and_usage(**fallback_kwargs)

            daily_costs = []
            grand_total = 0.0

            for result in response.get("ResultsByTime", []):
                date_str = result["TimePeriod"]["Start"]
                day_total = 0.0
                by_service = {}

                for group in result.get("Groups", []):
                    service = group["Keys"][0]
                    amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
                    if amount > 0.001:
                        by_service[service] = round(amount, 4)
                        day_total += amount

                daily_costs.append({
                    "date": date_str,
                    "total": round(day_total, 4),
                    "by_service": by_service,
                })
                grand_total += day_total

            result_data = {
                "available": True,
                "total": round(grand_total, 2),
                "daily_costs": daily_costs,
                "last_updated": datetime.now().isoformat(),
                "cached": False,
                "cache_age_minutes": 0,
                "error": None,
                "scope": "project" if tag_filtered else "account",
                "scope_note": None if tag_filtered else "Showing total account costs (cost allocation tags not available on linked accounts)",
            }
            self._write_cache(project_name, result_data)
            return result_data

        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code == "OptInRequired":
                return {
                    "available": False,
                    "error": "cost_explorer_not_enabled",
                    "error_message": (
                        "AWS Cost Explorer is not enabled for this account. "
                        "Enable it at https://console.aws.amazon.com/cost-management/home#/cost-explorer "
                        "— data takes 24 hours to appear after enabling."
                    ),
                }
            if code == "AccessDeniedException":
                return {
                    "available": False,
                    "error": "access_denied",
                    "error_message": (
                        "Missing IAM permission: ce:GetCostAndUsage. "
                        "Add this to your IAM user/role policy."
                    ),
                }
            # Unknown error — try returning stale cache
            return self._fallback_stale_cache(project_name, str(e))

        except (NoCredentialsError, BotoCoreError) as e:
            return self._fallback_stale_cache(project_name, str(e))

    def _fallback_stale_cache(self, project_name: str, error_msg: str) -> dict:
        """Return stale cache if available, otherwise error."""
        path = self._cache_path(project_name)
        if path.exists():
            try:
                data = json.loads(path.read_text())
                fetched = datetime.fromisoformat(data["fetched_at"])
                age = (datetime.now() - fetched).total_seconds() / 60
                data["cached"] = True
                data["stale"] = True
                data["cache_age_minutes"] = round(age, 1)
                data["error"] = f"Using cached data. API error: {error_msg}"
                return data
            except (json.JSONDecodeError, KeyError):
                pass
        return {
            "available": False,
            "error": "api_error",
            "error_message": f"AWS Cost Explorer error: {error_msg}",
        }

    # ------------------------------------------------------------------
    # Running estimate — real-time calculated costs
    # ------------------------------------------------------------------
    def calculate_running_estimate(self, project_name: str) -> dict:
        """Calculate estimated costs from instance types and uptime."""
        state = self._load_project_state(project_name)
        resources = self._load_project_resources(project_name)

        if not state and not resources:
            return {"available": False, "error": "No deployment data found"}

        deployment_type = (state or {}).get("deployment_type") or \
                          (resources or {}).get("deployment_type", "unknown")

        # Determine infrastructure uptime
        # Use deployed_at from resources (when infra went live), NOT state started_at (when terraform began)
        deployed_at_str = (resources or {}).get("deployed_at")
        status = (state or {}).get("status", "unknown")

        # Find when infrastructure was destroyed (from deployment history)
        destroyed_at_ts = self._find_destroy_timestamp(project_name)

        if deployed_at_str:
            deploy_ts = datetime.fromisoformat(deployed_at_str).timestamp()

            if destroyed_at_ts:
                # Destroyed — fixed window from deploy to destroy
                hours_running = (destroyed_at_ts - deploy_ts) / 3600
                is_active = False
            elif status in ("success",) and not (state or {}).get("purge_result"):
                # Active deployment — running since deployed
                hours_running = (time.time() - deploy_ts) / 3600
                is_active = True
            else:
                # Fallback: use state timestamps
                started_at = (state or {}).get("started_at")
                completed_at = (state or {}).get("completed_at")
                if started_at and completed_at:
                    start_ts = float(started_at) if isinstance(started_at, (int, float)) else \
                               datetime.fromisoformat(str(started_at)).timestamp()
                    end_ts = float(completed_at) if isinstance(completed_at, (int, float)) else \
                             datetime.fromisoformat(str(completed_at)).timestamp()
                    hours_running = (end_ts - start_ts) / 3600
                else:
                    hours_running = 0
                is_active = False
        else:
            hours_running = 0
            is_active = False

        hours_running = max(0, hours_running)

        # Build component list from resources
        components = []
        resource_list = (resources or {}).get("resources", [])

        ec2_instances = [r for r in resource_list if r.get("type") == "ec2"]
        nat_gateways = [r for r in resource_list if r.get("type") == "nat_gateway"]
        elastic_ips = [r for r in resource_list if r.get("type") == "elastic_ip"]
        s3_buckets = [r for r in resource_list if r.get("type") == "s3_bucket"]
        route53_zones = 1 if deployment_type and not deployment_type.startswith("goad-") else 0

        total_hourly = 0.0

        for inst in ec2_instances:
            itype = inst.get("instance_type", "t3.medium")
            hourly = EC2_HOURLY_RATES.get(itype, 0.05)
            name = inst.get("name", "EC2 Instance")
            # Extract role from name (e.g., "project-dev-c2-server-1" -> "C2 Server")
            role = self._extract_role(name, inst)
            components.append({
                "name": role,
                "instance_type": itype,
                "count": 1,
                "hourly": hourly,
                "subtotal": round(hourly * hours_running, 2),
            })
            total_hourly += hourly

        for _ in nat_gateways:
            hourly = FIXED_HOURLY["nat_gateway"]
            components.append({
                "name": "NAT Gateway",
                "instance_type": None,
                "count": 1,
                "hourly": hourly,
                "subtotal": round(hourly * hours_running, 2),
            })
            total_hourly += hourly

        for eip in elastic_ips:
            # EIPs are free when associated, $0.005/hr when idle
            hourly = FIXED_HOURLY["eip_idle"]
            components.append({
                "name": "Elastic IP",
                "instance_type": None,
                "count": 1,
                "hourly": hourly,
                "subtotal": round(hourly * hours_running, 2),
            })
            total_hourly += hourly

        if route53_zones > 0:
            monthly = FIXED_MONTHLY["route53_zone"]
            hourly_equiv = monthly / HOURS_PER_MONTH
            components.append({
                "name": "Route 53 Hosted Zone",
                "instance_type": None,
                "count": route53_zones,
                "hourly": round(hourly_equiv, 4),
                "subtotal": round(hourly_equiv * hours_running, 2),
            })
            total_hourly += hourly_equiv

        estimated_total = round(total_hourly * hours_running, 2)
        estimated_monthly = round(total_hourly * HOURS_PER_MONTH, 2)

        return {
            "available": True,
            "hourly_rate": round(total_hourly, 4),
            "hours_running": round(hours_running, 1),
            "estimated_total": estimated_total,
            "estimated_monthly": estimated_monthly,
            "by_component": components,
            "is_active": is_active,
            "deployment_type": deployment_type,
            "calculated_at": datetime.now().isoformat(),
        }

    def _extract_role(self, name: str, resource: dict) -> str:
        """Extract a human-readable role from an EC2 instance name or tags."""
        name_lower = name.lower()
        # Check specific component keywords (order matters — more specific first)
        if "bastion" in name_lower or "jumpbox" in name_lower:
            return "Bastion"
        if "redirect" in name_lower or "proxy" in name_lower:
            return "Redirector"
        if "attack" in name_lower:
            return "Attack Box"
        if "goad" in name_lower or "dc0" in name_lower or "srv0" in name_lower or "ws0" in name_lower:
            return "GOAD VM"
        if "teamserver" in name_lower or "team-server" in name_lower or "team_server" in name_lower:
            return "C2 Team Server"
        return resource.get("role") or "EC2 Instance"

    # ------------------------------------------------------------------
    # Combined summary
    # ------------------------------------------------------------------
    def get_cost_summary(self, project_name: str, force_refresh: bool = True) -> dict:
        """Orchestrator — returns actual + estimated + budget status."""
        settings = self.load_settings()
        budget = settings["budget_threshold"]

        actual = self.get_aws_costs(project_name, force_refresh)
        estimated = self.calculate_running_estimate(project_name)

        # Determine best total for budget calculation
        # Prefer actual costs if they have real data, otherwise use estimated
        actual_total = actual.get("total", 0) if actual.get("available") else 0
        estimated_total = estimated.get("estimated_total", 0) if estimated.get("available") else 0
        best_total = actual_total if actual_total > 0.01 else estimated_total

        budget_info = {
            "threshold": budget,
            "used_percent": round((best_total / budget) * 100, 1) if budget > 0 else 0,
            "remaining": round(budget - best_total, 2) if budget > 0 else 0,
        }

        return {
            "success": True,
            "project": project_name,
            "actual_costs": actual,
            "estimated_costs": estimated,
            "budget": budget_info,
        }

    # ------------------------------------------------------------------
    # All projects overview
    # ------------------------------------------------------------------
    def get_all_projects_summary(self) -> list:
        """Return cost overview for all known projects."""
        projects = []
        seen = set()

        # Active projects from state files
        if self.state_dir.exists():
            for state_file in self.state_dir.glob("*.state.json"):
                try:
                    state = json.loads(state_file.read_text())
                    name = state_file.stem.replace(".state", "")
                    if name in seen:
                        continue
                    seen.add(name)

                    status = state.get("status", "unknown")
                    completed_at = state.get("completed_at")
                    purge_result = state.get("purge_result")

                    # "active" = currently running OR successfully deployed and not destroyed/purged
                    # A project with status=success but completed_at set and purge_result means it was destroyed
                    if status == "running":
                        is_active = True
                    elif status == "success" and not purge_result:
                        # Check if resources still exist in deployment_resources.json
                        res = self._load_project_resources(name)
                        is_active = res is not None and len(res.get("resources", [])) > 0
                    else:
                        is_active = False

                    # Resolve deployment_type from state or resources file
                    dtype = state.get("deployment_type")
                    if not dtype:
                        res = self._load_project_resources(name)
                        dtype = (res or {}).get("deployment_type")

                    projects.append({
                        "name": name,
                        "status": "active" if is_active else "destroyed",
                        "deployment_type": dtype or "unknown",
                    })
                except (json.JSONDecodeError, IOError):
                    continue

        # Historical projects from resources file
        if self.resources_file.exists():
            try:
                all_res = json.loads(self.resources_file.read_text())
                for name, data in all_res.items():
                    if name in seen:
                        continue
                    seen.add(name)
                    projects.append({
                        "name": name,
                        "status": "destroyed",
                        "deployment_type": data.get("deployment_type", "unknown"),
                    })
            except (json.JSONDecodeError, IOError):
                pass

        return projects

    # ------------------------------------------------------------------
    # Aggregate monthly burn across all (active) deployments
    # ------------------------------------------------------------------
    def get_aggregate_monthly_burn(
        self,
        region: Optional[str] = None,
        include_destroyed: bool = False,
    ) -> dict:
        """Sum estimated monthly burn across deployments.

        Per Decision #19, D5 Dashboard launchpad's cost trend tile shows
        "all deployments" by default, with drill-down to per-deployment.

        Args:
            region: optional AWS region filter. Reserved for future use —
                running estimates are computed from local resource records,
                not Cost Explorer, so region filtering currently only
                annotates the response. The Cost Explorer path
                (`get_aws_costs`) does honour this argument when called
                directly.
            include_destroyed: when False (default) only deployments with
                status in {running, success, active} are summed.

        Returns:
            dict with keys: monthly_total, deployments[], region_filter,
            currency.
        """
        projects = self.get_all_projects_summary() or []
        total = 0.0
        per_project = []
        for p in projects:
            name = p.get("name") or p.get("project_name")
            if not name:
                continue
            status = p.get("status", "unknown")
            if not include_destroyed and status not in ("running", "success", "active"):
                continue
            try:
                est = self.calculate_running_estimate(name)
                monthly = est.get("estimated_monthly", 0) or 0 if est.get("available") else 0
            except Exception:
                monthly = 0
            total += monthly
            per_project.append({
                "project_name": name,
                "monthly": round(monthly, 2),
                "status": status,
            })
        return {
            "monthly_total": round(total, 2),
            "currency": "USD",
            "deployments": per_project,
            "region_filter": region,
        }

    # ------------------------------------------------------------------
    # Budget alert (lightweight — for Deployment Manager banner)
    # ------------------------------------------------------------------
    def get_budget_alert(self) -> dict:
        """Quick budget check across all active projects."""
        settings = self.load_settings()
        budget = settings["budget_threshold"]
        if budget <= 0:
            return {"enabled": False}

        total_spend = 0.0
        projects = self.get_all_projects_summary()
        active = [p for p in projects if p["status"] == "active"]

        for p in active:
            est = self.calculate_running_estimate(p["name"])
            if est.get("available"):
                total_spend += est.get("estimated_total", 0)

        used_pct = round((total_spend / budget) * 100, 1) if budget > 0 else 0

        return {
            "enabled": True,
            "threshold": budget,
            "total_spend": round(total_spend, 2),
            "used_percent": used_pct,
            "remaining": round(budget - total_spend, 2),
            "level": "danger" if used_pct >= 100 else "warning" if used_pct >= 80 else "ok",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _find_destroy_timestamp(self, project_name: str) -> Optional[float]:
        """Find when a project was destroyed from deployment history."""
        history_file = self.project_root / "logs" / "deployment_history.json"
        if not history_file.exists():
            return None
        try:
            history = json.loads(history_file.read_text())
            # Look for destroy events for this project (newest first)
            for entry in reversed(history):
                if entry.get("project_name") != project_name:
                    continue
                msg = (entry.get("message") or "").lower()
                if "destroy complete" in msg or "destroyed successfully" in msg:
                    ts_str = entry.get("timestamp", "")
                    if ts_str:
                        return datetime.fromisoformat(ts_str).timestamp()
        except (json.JSONDecodeError, IOError, ValueError):
            pass
        return None

    def _load_project_state(self, project_name: str) -> Optional[dict]:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_name)
        path = self.state_dir / f"{safe}.state.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, IOError):
                pass
        return None

    def _load_project_resources(self, project_name: str) -> Optional[dict]:
        if self.resources_file.exists():
            try:
                all_res = json.loads(self.resources_file.read_text())
                return all_res.get(project_name)
            except (json.JSONDecodeError, IOError):
                pass
        return None
