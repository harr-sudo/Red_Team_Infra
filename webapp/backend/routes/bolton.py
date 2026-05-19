"""Bolt-on REST API — vulnerability catalog, install, patch, probe.

Single Flask blueprint registered at ``/api/bolton``. Audit-attributed via
the existing ``g.operator`` middleware (set in
``webapp/backend/app.py:_resolve_operator``).

Surface area (see ``docs/internal/VULNERABLE_LAB_BOLTON_PLAN.md`` §9 and
its three refinement docs):

  Catalog
    GET    /api/bolton/vulns
    GET    /api/bolton/vulns/<vuln_id>
    GET    /api/bolton/vulns/<vuln_id>/coverage

  Host-contextualised catalog (compatibility refinement)
    GET    /api/bolton/labs/<lab>/hosts
    GET    /api/bolton/labs/<lab>/hosts/<host>/facts
    POST   /api/bolton/labs/<lab>/hosts/<host>/facts/refresh
    GET    /api/bolton/labs/<lab>/hosts/<host>/catalog
    GET    /api/bolton/labs/<lab>/hosts/<host>/installed

  Operations
    POST   /api/bolton/labs/<lab>/hosts/<host>/install/<vuln_id>
    POST   /api/bolton/labs/<lab>/hosts/<host>/uninstall/<vuln_id>
    POST   /api/bolton/labs/<lab>/hosts/<host>/patch/<vuln_id>
    POST   /api/bolton/labs/<lab>/hosts/<host>/patch-revert/<vuln_id>
    POST   /api/bolton/labs/<lab>/bulk

  Job lifecycle
    GET    /api/bolton/jobs
    GET    /api/bolton/jobs/<job_id>
    GET    /api/bolton/jobs/<job_id>/log
    POST   /api/bolton/jobs/<job_id>/cancel
    POST   /api/bolton/jobs/<job_id>/agent-intervene
    POST   /api/bolton/jobs/<job_id>/agent-approve
    POST   /api/bolton/jobs/<job_id>/agent-reject

  Detection coverage + probe (ttp/elastic refinement)
    POST   /api/bolton/vulns/<vuln_id>/probe
    GET    /api/bolton/probes/<probe_job_id>
    POST   /api/bolton/vulns/<vuln_id>/generate-rule
    GET    /api/bolton/detection/gaps
    GET    /api/bolton/coverage/navigator-layer

Service-layer dependencies (provided by Agent B; mocked in tests):

  webapp.backend.services.bolton_catalog_service
  webapp.backend.services.bolton_facts_service
  webapp.backend.services.bolton_compatibility
  webapp.backend.services.bolton_install_service
  webapp.backend.services.bolton_jobs_service
  webapp.backend.services.bolton_probe_service
  webapp.backend.services.bolton_coverage_service

Each service module is imported lazily inside the route handler so the
blueprint imports cleanly even when Agent B hasn't shipped yet.
"""
from __future__ import annotations

import importlib
import logging
import uuid
from typing import Any, Optional

from flask import Blueprint, Response, g, jsonify, request, stream_with_context

from webapp.backend.routes import bolton_schemas as schemas
from webapp.backend.services import audit_service

_log = logging.getLogger(__name__)

bp = Blueprint("bolton", __name__, url_prefix="/api/bolton")


# ─── Audit action namespace ─────────────────────────────────────────────────
# Every state-changing route emits one of these. Stable strings — the
# activity feed renders them; do not rename without updating audit
# consumers.
_AUDIT_ACTIONS = (
    "bolton.facts.refresh",
    "bolton.install",
    "bolton.uninstall",
    "bolton.patch",
    "bolton.patch_revert",
    "bolton.bulk",
    "bolton.job.cancel",
    "bolton.job.agent_intervene",
    "bolton.agent.invoke",
    "bolton.agent.tool_call",
    "bolton.agent.approve",
    "bolton.agent.reject",
    "bolton.agent.retry",
    "bolton.probe",
    "bolton.generate_rule",
)


# ─── Helpers ────────────────────────────────────────────────────────────────

def _operator_id() -> str:
    """Return the operator id from ``g``, defaulting to ``unknown``.

    Mirrors the pattern used in ``operators.py`` and ``audit.py`` — never
    raises if the middleware hasn't populated ``g.operator``.
    """
    actor = getattr(g, "operator", None) or {"id": "unknown"}
    return actor.get("id", "unknown")


def _audit(action: str, *, target: Optional[str] = None,
           project: Optional[str] = None,
           details: Optional[dict[str, Any]] = None) -> None:
    """Write one audit entry under the operator from ``g``.

    Wraps ``audit_service.write`` so route handlers stay terse. The audit
    service itself never raises — see ``audit_service.write``'s docstring.
    """
    audit_service.write(
        _operator_id(),
        action,
        target=target,
        project=project,
        details=details,
    )


def _svc(module_name: str) -> Any:
    """Lazy import a service module.

    Returns the module if importable; raises ``ImportError`` otherwise.
    Tests monkeypatch the module's attributes directly, so this still
    works under mocking (the patched attribute lookup happens after the
    import).
    """
    return importlib.import_module(module_name)


def _err(message: str, status: int, **extra: Any) -> tuple[Any, int]:
    """Return a uniform JSON error envelope."""
    body = {"success": False, "error": message}
    body.update(extra)
    return jsonify(body), status


# ─── Catalog ────────────────────────────────────────────────────────────────

@bp.route("/vulns", methods=["GET"])
def list_vulns():
    """List the vulnerability catalog as a slim descriptor array.

    ---
    summary: List all bolt-on vulnerability descriptors.
    parameters:
      - in: query
        name: category
        schema: { type: string }
      - in: query
        name: target_os
        schema: { type: string }
      - in: query
        name: coverage_status
        schema: { type: string, enum: [covered, partial, no-rule, rule-stale] }
      - in: query
        name: search
        schema: { type: string }
    responses:
      200:
        description: |
          ``{success, vulns: [VulnSummary], total}`` — descriptors are slim
          (id, name, category, mitre, coverage_status, summary_meta).
          Long fields (install scripts, full YAML) are excluded; fetch
          them via ``/vulns/<id>`` when needed.
    """
    try:
        svc = _svc("webapp.backend.services.bolton_catalog_service")
    except ImportError as e:
        _log.warning("bolton_catalog_service unavailable: %s", e)
        return _err("catalog service unavailable", 503)

    vulns = svc.list_summaries(
        category=request.args.get("category"),
        target_os=request.args.get("target_os"),
        coverage_status=request.args.get("coverage_status"),
        search=request.args.get("search"),
    )
    return jsonify({"success": True, "vulns": vulns, "total": len(vulns)})


@bp.route("/vulns/<vuln_id>", methods=["GET"])
def get_vuln(vuln_id: str):
    """Return the full descriptor for one vulnerability.

    ---
    summary: Fetch full vulnerability descriptor by id.
    parameters:
      - in: path
        name: vuln_id
        required: true
        schema: { type: string }
    responses:
      200: { description: "Full descriptor object." }
      404: { description: "No descriptor with that id." }
    """
    svc = _svc("webapp.backend.services.bolton_catalog_service")
    vuln = svc.get(vuln_id)
    if vuln is None:
        return _err(f"vuln '{vuln_id}' not found", 404)
    return jsonify({"success": True, "vuln": vuln})


@bp.route("/vulns/<vuln_id>/coverage", methods=["GET"])
def get_coverage(vuln_id: str):
    """Detection coverage detail (Elastic rules, freshness, fallback template).

    ---
    summary: Get detection coverage detail for a vulnerability.
    parameters:
      - in: path
        name: vuln_id
        required: true
        schema: { type: string }
      - in: query
        name: host
        schema: { type: string }
        description: Optional - filters probe_history to one host.
    responses:
      200:
        description: |
          ``{coverage_status, rules: [...], mitre: [...], fallback_template,
          probe_history: [...]}``
      404: { description: "No descriptor with that id." }
    """
    svc = _svc("webapp.backend.services.bolton_coverage_service")
    try:
        coverage = svc.get_for_vuln(vuln_id, host=request.args.get("host"))
    except KeyError:
        return _err(f"vuln '{vuln_id}' not found", 404)
    return jsonify({"success": True, **coverage})


# ─── Host facts + host-contextualised catalog ───────────────────────────────

@bp.route("/labs/<lab>/hosts", methods=["GET"])
def list_hosts(lab: str):
    """List the hosts in a lab with a quick summary of installed bolt-ons.

    ---
    summary: Hosts in a lab + installed-bolton counts.
    parameters:
      - in: path
        name: lab
        required: true
        schema: { type: string }
    responses:
      200:
        description: |
          ``{hosts: [{name, role, os, ip, installed_count}], lab}``
      404: { description: "Lab not deployed or not recognized." }
    """
    svc = _svc("webapp.backend.services.bolton_facts_service")
    try:
        hosts = svc.list_hosts(lab)
    except KeyError:
        return _err(f"lab '{lab}' not found", 404)
    return jsonify({"success": True, "lab": lab, "hosts": hosts})


@bp.route("/labs/<lab>/hosts/<host>/facts", methods=["GET"])
def get_host_facts(lab: str, host: str):
    """Return the cached host fact bundle.

    ---
    summary: Cached host facts for the compatibility resolver.
    parameters:
      - in: path
        name: lab
        required: true
      - in: path
        name: host
        required: true
      - in: query
        name: force_refresh
        schema: { type: boolean }
      - in: query
        name: include_raw
        schema: { type: boolean }
    responses:
      200: { description: "Host facts bundle (see BOLTON_REFINEMENT_compatibility.md §2.2)" }
      404: { description: "Host not in lab, or facts never collected." }
      503: { description: "Host unreachable on last attempt." }
    """
    svc = _svc("webapp.backend.services.bolton_facts_service")
    force = request.args.get("force_refresh", "").lower() in ("1", "true", "yes")
    include_raw = request.args.get("include_raw", "").lower() in ("1", "true", "yes")
    try:
        facts = svc.get_facts(lab, host, force_refresh=force, include_raw=include_raw)
    except KeyError:
        return _err(f"host '{host}' in lab '{lab}' not found", 404)
    except svc.HostUnreachable as e:  # type: ignore[attr-defined]
        return _err("host_unreachable", 503,
                    last_known_collected_at=getattr(e, "last_collected_at", None),
                    last_error=str(e))
    return jsonify({"success": True, **facts})


@bp.route("/labs/<lab>/hosts/<host>/facts/refresh", methods=["POST"])
def refresh_host_facts(lab: str, host: str):
    """Force a re-probe of host facts. Blocking; returns fresh bundle.

    ---
    summary: Force re-probe of host facts.
    parameters:
      - in: path
        name: lab
        required: true
      - in: path
        name: host
        required: true
    requestBody:
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/FactsRefreshRequest'
    responses:
      200: { description: "Fresh host facts bundle." }
      503: { description: "Host unreachable." }
      504: { description: "Probe timed out (>30s)." }
    """
    body = request.get_json(silent=True) or {}
    try:
        req = schemas.FactsRefreshRequest.model_validate(body)
    except Exception as e:
        return _err(f"invalid body: {e}", 400)
    deep = bool(getattr(req, "deep_probe", False))

    svc = _svc("webapp.backend.services.bolton_facts_service")
    try:
        facts = svc.refresh_facts(lab, host, deep_probe=deep)
    except KeyError:
        return _err(f"host '{host}' in lab '{lab}' not found", 404)
    except svc.HostUnreachable as e:  # type: ignore[attr-defined]
        return _err("host_unreachable", 503, last_error=str(e))
    except svc.ProbeTimeout as e:  # type: ignore[attr-defined]
        return _err("probe_timeout", 504, last_error=str(e))

    _audit("bolton.facts.refresh",
           target=host,
           project=lab,
           details={"deep_probe": deep})
    return jsonify({"success": True, **facts})


@bp.route("/labs/<lab>/hosts/<host>/catalog", methods=["GET"])
def host_catalog(lab: str, host: str):
    """Return the catalog annotated with compatibility state for one host.

    ---
    summary: Full catalog × compatibility state per vuln.
    parameters:
      - in: path
        name: lab
        required: true
      - in: path
        name: host
        required: true
      - in: query
        name: category
        schema: { type: string }
      - in: query
        name: state
        schema: { type: array, items: { type: string } }
        description: |
          One of INSTALLABLE, INCOMPATIBLE_OS, INCOMPATIBLE_ROLE,
          MISSING_PREREQ, CONFLICTS_WITH_INSTALLED, ALREADY_INSTALLED,
          MISSING_SOFTWARE, PATCHED. Repeatable (OR semantics).
      - in: query
        name: search
        schema: { type: string }
    responses:
      200: { description: "CompatibilityCatalogResponse" }
      404: { description: "Host or lab not found." }
      409: { description: "Facts never collected — call /facts/refresh first." }
    """
    svc = _svc("webapp.backend.services.bolton_compatibility")
    states = request.args.getlist("state") or None
    try:
        result = svc.host_catalog(
            lab=lab,
            host=host,
            category=request.args.get("category"),
            states=states,
            search=request.args.get("search"),
        )
    except KeyError:
        return _err(f"host '{host}' in lab '{lab}' not found", 404)
    except svc.FactsMissing as e:  # type: ignore[attr-defined]
        return _err("facts_missing", 409,
                    hint=f"POST /api/bolton/labs/{lab}/hosts/{host}/facts/refresh",
                    detail=str(e))
    return jsonify({"success": True, **result})


@bp.route("/labs/<lab>/hosts/<host>/installed", methods=["GET"])
def host_installed(lab: str, host: str):
    """Return bolt-ons installed on this host.

    ---
    summary: Installed bolt-ons on a single host.
    responses:
      200: { description: "{installed: [InstalledRecord]}" }
      404: { description: "Host or lab not found." }
    """
    svc = _svc("webapp.backend.services.bolton_facts_service")
    try:
        installed = svc.get_installed(lab, host)
    except KeyError:
        return _err(f"host '{host}' in lab '{lab}' not found", 404)
    return jsonify({"success": True, "lab": lab, "host": host,
                    "installed": installed})


# ─── Operations: install / uninstall / patch / patch-revert ─────────────────

def _dispatch_op(lab: str, host: str, vuln_id: str, op: str,
                 audit_action: str):
    """Shared implementation for the four single-op dispatch endpoints.

    All four endpoints share an identical contract — body shape
    (``InstallRequest``), success envelope (``JobDispatchResponse``),
    error mapping (404 unknown vuln/host, 409 compatibility refusal).
    """
    body = request.get_json(silent=True) or {}
    try:
        req = schemas.InstallRequest.model_validate(body)
    except Exception as e:
        return _err(f"invalid body: {e}", 400)

    svc = _svc("webapp.backend.services.bolton_install_service")
    try:
        result = svc.dispatch(
            op=op,
            lab=lab,
            host=host,
            vuln_id=vuln_id,
            role_vars=getattr(req, "role_vars", None) or {},
            run_probe=bool(getattr(req, "run_probe", False)),
            confirm_no_detection=bool(getattr(req, "confirm_no_detection", False)),
            actor=_operator_id(),
        )
    except KeyError as e:
        return _err(str(e) or "not_found", 404)
    except svc.CompatibilityRefused as e:  # type: ignore[attr-defined]
        return _err("compatibility_refused", 409,
                    state=getattr(e, "state", None),
                    reason=str(e))

    _audit(audit_action,
           target=f"{host}:{vuln_id}",
           project=lab,
           details={
               "vuln_id": vuln_id,
               "host": host,
               "lab": lab,
               "job_id": result.get("job_id"),
               "run_probe": bool(getattr(req, "run_probe", False)),
           })

    resp = schemas.JobDispatchResponse(
        success=True,
        job_id=result["job_id"],
        action=audit_action,
        lab=lab,
        host=host,
        vuln_id=vuln_id,
        estimated_time_seconds=result.get("estimated_time_seconds"),
        message=result.get("message"),
    )
    return jsonify(resp.model_dump())


@bp.route("/labs/<lab>/hosts/<host>/install/<vuln_id>", methods=["POST"])
def install(lab: str, host: str, vuln_id: str):
    """Dispatch an install job.

    ---
    summary: Dispatch a bolt-on install on (lab, host, vuln).
    parameters:
      - in: path
        name: lab
        required: true
      - in: path
        name: host
        required: true
      - in: path
        name: vuln_id
        required: true
    requestBody:
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/InstallRequest'
    responses:
      200: { description: "JobDispatchResponse" }
      400: { description: "Invalid body." }
      404: { description: "Unknown vuln/host/lab." }
      409: { description: "Compatibility refused — see ``state`` and ``reason``." }
    """
    return _dispatch_op(lab, host, vuln_id, op="install",
                        audit_action="bolton.install")


@bp.route("/labs/<lab>/hosts/<host>/uninstall/<vuln_id>", methods=["POST"])
def uninstall(lab: str, host: str, vuln_id: str):
    """Dispatch an uninstall job.

    ---
    summary: Dispatch a bolt-on uninstall on (lab, host, vuln).
    responses:
      200: { description: "JobDispatchResponse" }
      400: { description: "Invalid body." }
      404: { description: "Unknown vuln/host/lab." }
      409: { description: "Transition not allowed from current state." }
    """
    return _dispatch_op(lab, host, vuln_id, op="uninstall",
                        audit_action="bolton.uninstall")


@bp.route("/labs/<lab>/hosts/<host>/patch/<vuln_id>", methods=["POST"])
def patch(lab: str, host: str, vuln_id: str):
    """Dispatch a real-world patch job (vendor remediation).

    ---
    summary: Apply the descriptor's ``patch`` block to a host.
    responses:
      200: { description: "JobDispatchResponse" }
      400: { description: "Invalid body." }
      404: { description: "Unknown vuln/host/lab." }
      409: { description: "Vuln not in INSTALLED state — patch refused." }
    """
    return _dispatch_op(lab, host, vuln_id, op="patch",
                        audit_action="bolton.patch")


@bp.route("/labs/<lab>/hosts/<host>/patch-revert/<vuln_id>", methods=["POST"])
def patch_revert(lab: str, host: str, vuln_id: str):
    """Reverse a patch — re-expose the vulnerability (training-loop primitive).

    ---
    summary: Revert a previously applied patch.
    responses:
      200: { description: "JobDispatchResponse" }
      400: { description: "Invalid body." }
      404: { description: "Unknown vuln/host/lab." }
      409: { description: "Vuln not in PATCHED state, or rollback_supported=false." }
    """
    return _dispatch_op(lab, host, vuln_id, op="patch_revert",
                        audit_action="bolton.patch_revert")


@bp.route("/labs/<lab>/bulk", methods=["POST"])
def bulk(lab: str):
    """Batch dispatch — cross-product of hosts × vuln_ids for one action.

    ---
    summary: Bulk install / uninstall / patch / patch-revert.
    parameters:
      - in: path
        name: lab
        required: true
    requestBody:
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/BulkOperationRequest'
    responses:
      200:
        description: |
          ``BulkDispatchResponse`` — one job_id per (host, vuln) pair plus an
          ``errors`` array for any pairs that failed to enqueue. Partial
          success is *valid*; the envelope is always 200 unless the request
          body itself was malformed.
      400: { description: "Invalid body." }
    """
    body = request.get_json(silent=True) or {}
    try:
        req = schemas.BulkOperationRequest.model_validate(body)
    except Exception as e:
        return _err(f"invalid body: {e}", 400)

    action = (getattr(req, "action", "") or "").strip()
    if action not in ("install", "uninstall", "patch", "patch_revert"):
        return _err(f"unknown action '{action}'", 400)
    hosts = list(getattr(req, "hosts", []) or [])
    vuln_ids = list(getattr(req, "vuln_ids", []) or [])
    if not hosts or not vuln_ids:
        return _err("hosts and vuln_ids must be non-empty", 400)

    svc = _svc("webapp.backend.services.bolton_install_service")
    jobs: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for host in hosts:
        for vid in vuln_ids:
            try:
                result = svc.dispatch(
                    op=action,
                    lab=lab,
                    host=host,
                    vuln_id=vid,
                    role_vars=getattr(req, "role_vars", None) or {},
                    run_probe=False,
                    confirm_no_detection=False,
                    actor=_operator_id(),
                )
                jobs.append({
                    "job_id": result["job_id"],
                    "lab": lab,
                    "host": host,
                    "vuln_id": vid,
                })
            except Exception as e:  # noqa: BLE001
                errors.append({
                    "host": host,
                    "vuln_id": vid,
                    "error": str(e),
                })

    _audit("bolton.bulk",
           project=lab,
           details={
               "action": action,
               "host_count": len(hosts),
               "vuln_count": len(vuln_ids),
               "job_count": len(jobs),
               "error_count": len(errors),
           })

    resp = schemas.BulkDispatchResponse(
        success=True,
        job_count=len(jobs),
        jobs=jobs,
        errors=errors,
    )
    return jsonify(resp.model_dump())


# ─── Job lifecycle ──────────────────────────────────────────────────────────

@bp.route("/jobs", methods=["GET"])
def list_jobs():
    """List jobs with optional filters.

    ---
    summary: List bolt-on jobs.
    parameters:
      - in: query
        name: lab
        schema: { type: string }
      - in: query
        name: host
        schema: { type: string }
      - in: query
        name: status
        schema: { type: string, enum: [QUEUED, RUNNING, VERIFYING, DONE, STUCK, FAILED, CANCELED] }
      - in: query
        name: action
        schema: { type: string, enum: [install, uninstall, patch, patch_revert] }
      - in: query
        name: limit
        schema: { type: integer, default: 50 }
    responses:
      200: { description: "{jobs: [...], total}" }
    """
    svc = _svc("webapp.backend.services.bolton_jobs_service")
    try:
        limit = min(int(request.args.get("limit", 50)), 500)
    except (TypeError, ValueError):
        limit = 50
    jobs = svc.list_jobs(
        lab=request.args.get("lab"),
        host=request.args.get("host"),
        status=request.args.get("status"),
        action=request.args.get("action"),
        limit=limit,
    )
    return jsonify({"success": True, "jobs": jobs, "total": len(jobs)})


@bp.route("/jobs/<job_id>", methods=["GET"])
def get_job(job_id: str):
    """Job details + tail log.

    ---
    summary: Get a job's state, steps, and log tail.
    parameters:
      - in: path
        name: job_id
        required: true
        schema: { type: string }
      - in: query
        name: since
        schema: { type: integer }
        description: Byte offset; only log bytes after this position are returned.
    responses:
      200: { description: "{status, steps, log_tail, agent_state?}" }
      404: { description: "Unknown job." }
    """
    svc = _svc("webapp.backend.services.bolton_jobs_service")
    try:
        since = int(request.args.get("since", 0))
    except (TypeError, ValueError):
        since = 0
    job = svc.get_job(job_id, log_since=since)
    if job is None:
        return _err(f"job '{job_id}' not found", 404)
    return jsonify({"success": True, **job})


@bp.route("/jobs/<job_id>/log", methods=["GET"])
def stream_job_log(job_id: str):
    """Stream job log as Server-Sent Events.

    ---
    summary: SSE log stream for a job.
    parameters:
      - in: path
        name: job_id
        required: true
    responses:
      200:
        description: |
          ``text/event-stream`` — newline-delimited ``data: <line>\\n\\n``
          events. Stream terminates when the job reaches a terminal state.
      404: { description: "Unknown job." }
    """
    svc = _svc("webapp.backend.services.bolton_jobs_service")
    if not svc.job_exists(job_id):
        return _err(f"job '{job_id}' not found", 404)

    def _gen():
        for line in svc.stream_log(job_id):
            yield f"data: {line}\n\n"

    return Response(stream_with_context(_gen()),
                    mimetype="text/event-stream")


@bp.route("/jobs/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id: str):
    """Request cancellation of a running job.

    ---
    summary: Cancel a job.
    parameters:
      - in: path
        name: job_id
        required: true
    responses:
      200: { description: "{status: 'CANCELING' | 'CANCELED'}" }
      404: { description: "Unknown job." }
      409: { description: "Job already in terminal state." }
    """
    svc = _svc("webapp.backend.services.bolton_jobs_service")
    try:
        result = svc.cancel(job_id)
    except KeyError:
        return _err(f"job '{job_id}' not found", 404)
    except svc.NotCancellable as e:  # type: ignore[attr-defined]
        return _err("not_cancellable", 409, reason=str(e))

    _audit("bolton.job.cancel", target=job_id)
    return jsonify({"success": True, **result})


@bp.route("/jobs/<job_id>/agent-intervene", methods=["POST"])
def agent_intervene(job_id: str):
    """Invoke the Claude-powered agentic fallback on a stuck job.

    Calls into ``bolton_agent_service.invoke_agent`` which builds a
    bounded context, runs at most ``MAX_TOOL_INVOCATIONS`` read-only
    diagnostic tools, and returns an ``AgentProposal`` for the operator
    to review. Hard limits (tool count, wall-clock) are enforced inside
    the service; this route is a thin adapter.

    ---
    summary: Invoke agentic fallback on a stuck job.
    parameters:
      - in: path
        name: job_id
        required: true
    responses:
      200: { description: "{proposal: AgentProposal}" }
      404: { description: "Unknown job." }
      409: { description: "Job is not in STUCK state." }
      503: { description: "ANTHROPIC_API_KEY not configured." }
    """
    jobs_svc = _svc("webapp.backend.services.bolton_jobs_service")
    if not jobs_svc.job_exists(job_id):
        return _err(f"job '{job_id}' not found", 404)

    agent_svc = _svc("webapp.backend.services.bolton_agent_service")
    try:
        proposal = agent_svc.invoke_agent(job_id, _operator_id())
    except RuntimeError as e:
        # API key missing OR wall-clock exceeded — both surface as 503.
        return _err(str(e), 503)
    except KeyError as e:
        return _err(str(e), 404)
    except ValueError as e:
        # Job not in STUCK state.
        return _err(str(e), 409)
    except Exception as e:  # noqa: BLE001
        _log.exception("agent invocation crashed for job=%s", job_id)
        return _err(f"agent invocation failed: {e}", 500)

    _audit("bolton.job.agent_intervene",
           target=job_id,
           details={
               "proposed_action": getattr(proposal, "proposed_action", None),
               "tool_calls": len(getattr(proposal, "diagnostic_outputs", []) or []),
           })

    return jsonify({
        "success": True,
        "job_id": job_id,
        "proposal": agent_svc.proposal_to_dict(proposal),
    })


@bp.route("/jobs/<job_id>/agent-approve", methods=["POST"])
def agent_approve(job_id: str):
    """Operator approves an agent proposal — dispatch the retry.

    Body: ``{modifications: {input_name: value, ...}}``. The
    install service re-queues the job with the modified inputs; the
    audit log gets a ``bolton.agent.approve`` + ``bolton.agent.retry``
    pair.

    ---
    summary: Approve a stuck-job agent retry proposal.
    parameters:
      - in: path
        name: job_id
        required: true
    requestBody:
      content:
        application/json:
          schema:
            type: object
            properties:
              modifications: { type: object }
              proposal_id: { type: string }
    responses:
      200: { description: "{new_job_id, status: 'queued'}" }
      404: { description: "Unknown job." }
      409: { description: "Job not in STUCK state." }
    """
    body = request.get_json(silent=True) or {}
    modifications = body.get("modifications") or {}
    proposal_id = body.get("proposal_id")

    if not isinstance(modifications, dict):
        return _err("modifications must be an object", 400)

    install_svc = _svc("webapp.backend.services.bolton_install_service")
    try:
        new_job = install_svc.retry_with_modifications(
            job_id, modifications, operator=_operator_id()
        )
    except KeyError as e:
        return _err(str(e), 404)
    except ValueError as e:
        return _err(str(e), 409)

    _audit("bolton.agent.approve",
           target=job_id,
           details={
               "proposal_id": proposal_id,
               "new_job_id": getattr(new_job, "id", None),
               "modifications": modifications,
           })

    return jsonify({
        "success": True,
        "new_job_id": getattr(new_job, "id", None),
        "status": "queued",
        "modifications": modifications,
    })


@bp.route("/jobs/<job_id>/agent-reject", methods=["POST"])
def agent_reject(job_id: str):
    """Operator rejects an agent proposal — audit only, no state change.

    The job stays in STUCK so the operator can either invoke the agent
    again, mark it failed manually via the existing cancel path, or
    apply a manual fix outside the dashboard.

    ---
    summary: Reject a stuck-job agent retry proposal.
    parameters:
      - in: path
        name: job_id
        required: true
    requestBody:
      content:
        application/json:
          schema:
            type: object
            properties:
              proposal_id: { type: string }
              reason: { type: string }
    responses:
      200: { description: "{status: 'rejected'}" }
      404: { description: "Unknown job." }
    """
    body = request.get_json(silent=True) or {}
    proposal_id = body.get("proposal_id")
    reason = body.get("reason")

    jobs_svc = _svc("webapp.backend.services.bolton_jobs_service")
    if not jobs_svc.job_exists(job_id):
        return _err(f"job '{job_id}' not found", 404)

    _audit("bolton.agent.reject",
           target=job_id,
           details={"proposal_id": proposal_id, "reason": reason})

    return jsonify({
        "success": True,
        "status": "rejected",
        "job_id": job_id,
    })


# ─── Detection probe / generate-rule / gaps / Navigator ────────────────────

@bp.route("/vulns/<vuln_id>/probe", methods=["POST"])
def vuln_probe(vuln_id: str):
    """Run the descriptor's synthetic exploit probe and correlate with Elastic.

    ---
    summary: Trigger synthetic exploit probe; verifies Elastic rule fires.
    parameters:
      - in: path
        name: vuln_id
        required: true
        schema: { type: string }
    requestBody:
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ProbeRequest'
    responses:
      200: { description: "{probe_job_id}" }
      400: { description: "Invalid body (missing lab/host)." }
      404: { description: "Vuln has no trigger_probe block." }
    """
    body = request.get_json(silent=True) or {}
    try:
        req = schemas.ProbeRequest.model_validate(body)
    except Exception as e:
        return _err(f"invalid body: {e}", 400)
    if not getattr(req, "lab", None) or not getattr(req, "host", None):
        return _err("lab and host are required", 400)

    svc = _svc("webapp.backend.services.bolton_probe_service")
    try:
        result = svc.run_probe(
            vuln_id=vuln_id,
            lab=req.lab,
            host=req.host,
            window_seconds=getattr(req, "window_seconds", None),
            actor=_operator_id(),
        )
    except KeyError:
        return _err(f"vuln '{vuln_id}' has no trigger_probe", 404)

    _audit("bolton.probe",
           target=f"{req.host}:{vuln_id}",
           project=req.lab,
           details={"vuln_id": vuln_id, "probe_job_id": result.get("probe_job_id")})

    return jsonify({"success": True, **result})


@bp.route("/probes/<probe_job_id>", methods=["GET"])
def get_probe(probe_job_id: str):
    """Probe job status.

    ---
    summary: Get probe job status + Elastic-alert correlation result.
    parameters:
      - in: path
        name: probe_job_id
        required: true
    responses:
      200:
        description: |
          ``{status, probe_stdout, alerts_received: [...],
          result: verified | no-alert | probe-failed | probe-only}``
      404: { description: "Unknown probe job." }
    """
    svc = _svc("webapp.backend.services.bolton_probe_service")
    probe = svc.get_probe(probe_job_id)
    if probe is None:
        return _err(f"probe '{probe_job_id}' not found", 404)
    return jsonify({"success": True, **probe})


@bp.route("/vulns/<vuln_id>/generate-rule", methods=["POST"])
def generate_rule(vuln_id: str):
    """Generate a starter Elastic rule TOML from a fallback template
    (Phase 1 stub).

    ---
    summary: Seed a draft Elastic detection rule from the fallback template.
    parameters:
      - in: path
        name: vuln_id
        required: true
    requestBody:
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/GenerateRuleRequest'
    responses:
      200: { description: "{draft_rule_toml, template_used, new_uuid}" }
      404: { description: "Unknown vuln." }
      409: { description: "No fallback_rule_template defined and mitre=none." }
    """
    body = request.get_json(silent=True) or {}
    try:
        schemas.GenerateRuleRequest.model_validate(body)
    except Exception as e:
        return _err(f"invalid body: {e}", 400)

    # Phase 1 stub — Agent B will wire a Jinja renderer in Phase 2.
    # Verify the vuln exists so callers get a sensible 404 / 409.
    try:
        catalog = _svc("webapp.backend.services.bolton_catalog_service")
        vuln = catalog.get(vuln_id)
        if vuln is None:
            return _err(f"vuln '{vuln_id}' not found", 404)
    except ImportError:
        vuln = {"id": vuln_id}

    new_uuid = str(uuid.uuid4())
    stub_toml = (
        f"# Auto-generated stub for {vuln_id}\n"
        f"# Phase 1 placeholder — replace with proper Jinja-rendered TOML\n"
        f"[metadata]\n"
        f"maturity = \"development\"\n"
        f"\n"
        f"[rule]\n"
        f"author = [\"Red Team Infra Bolt-On Framework\"]\n"
        f"description = \"Starter detection rule for {vuln_id}\"\n"
        f"name = \"Detect {vuln_id}\"\n"
        f"rule_id = \"{new_uuid}\"\n"
        f"severity = \"medium\"\n"
        f"type = \"eql\"\n"
        f"\n"
        f"query = '''\n"
        f"// TODO: replace with detection EQL/KQL\n"
        f"any where true\n"
        f"'''\n"
    )

    _audit("bolton.generate_rule",
           target=vuln_id,
           details={"new_uuid": new_uuid, "stubbed": True})

    return jsonify({
        "success": True,
        "draft_rule_toml": stub_toml,
        "template_used": "phase1-stub",
        "new_uuid": new_uuid,
        "stubbed": True,
        "message": "Phase 1 placeholder — Jinja renderer wired in Phase 2.",
    })


@bp.route("/detection/gaps", methods=["GET"])
def detection_gaps():
    """List installed bolt-ons that have no detection coverage.

    ---
    summary: Detection-gap backlog.
    parameters:
      - in: query
        name: lab
        schema: { type: string }
      - in: query
        name: state
        schema: { type: string, enum: [no-rule, partial, rule-stale] }
    responses:
      200:
        description: |
          ``{gaps: [{vuln_id, name, coverage_status, fallback_template?, ...}],
          summary: {covered, partial, no_rule, stale}}``
    """
    svc = _svc("webapp.backend.services.bolton_coverage_service")
    result = svc.detection_gaps(
        lab=request.args.get("lab"),
        state=request.args.get("state"),
    )
    return jsonify({"success": True, **result})


@bp.route("/coverage/navigator-layer", methods=["GET"])
def navigator_layer():
    """Export a MITRE ATT&CK Navigator JSON layer.

    ---
    summary: MITRE Navigator layer for the lab's bolt-on coverage.
    parameters:
      - in: query
        name: lab
        schema: { type: string }
      - in: query
        name: installed_only
        schema: { type: boolean, default: true }
    responses:
      200: { description: "{layer: <navigator-layer-json>}" }
      404: { description: "Lab not found." }
    """
    svc = _svc("webapp.backend.services.bolton_coverage_service")
    lab = request.args.get("lab")
    installed_only = request.args.get("installed_only", "true").lower() in ("1", "true", "yes")
    try:
        layer = svc.navigator_layer(lab=lab, installed_only=installed_only)
    except KeyError:
        return _err(f"lab '{lab}' not found", 404)
    return jsonify({"success": True, "layer": layer})
