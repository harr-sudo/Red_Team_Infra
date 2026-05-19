"""Bolt-on Phase 3a — agentic fallback service tests.

The Anthropic SDK is mocked end-to-end. We never make a real API call;
instead ``anthropic.Anthropic`` is replaced with a class whose
``messages.create`` returns a pre-baked response object containing either
``text`` blocks (final proposal) or ``tool_use`` blocks (diagnostic
calls). Tests cover:

  - ANTHROPIC_API_KEY enforcement
  - System prompt / user message structure
  - Tool dispatch table mapping
  - Hard limit enforcement (tool count, wall-clock)
  - Audit log emission for invoke + tool_call + approve/reject
  - Proposal serialisation + retry_inputs validation
"""
from __future__ import annotations

import json
import os
import sys
import time
import types
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest


# ──────────────────────────────────────────────────────────────────────
# Fake anthropic SDK
# ──────────────────────────────────────────────────────────────────────

@dataclass
class _Block:
    type: str
    text: str = ""
    id: str = "tu_1"
    name: str = ""
    input: dict = None  # type: ignore[assignment]


@dataclass
class _FakeResponse:
    content: list
    stop_reason: str = "end_turn"


class _FakeClient:
    """Anthropic.Anthropic stand-in. Pops responses off a list."""

    def __init__(self, *, api_key=None, **_):
        self.api_key = api_key
        self.messages = MagicMock()
        self.messages.create = MagicMock()


@pytest.fixture
def fake_anthropic(monkeypatch):
    """Install a fake ``anthropic`` module into sys.modules.

    Yields the ``_FakeClient`` class so tests can configure its
    ``messages.create`` return values per case.
    """
    mod = types.ModuleType("anthropic")
    mod.Anthropic = _FakeClient
    monkeypatch.setitem(sys.modules, "anthropic", mod)
    yield _FakeClient
    # Cleanup happens automatically via monkeypatch.


@pytest.fixture
def env_api_key(monkeypatch):
    """Set a fake ANTHROPIC_API_KEY for tests that need the agent to start."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")


# ──────────────────────────────────────────────────────────────────────
# Fake install / facts / catalog services
# ──────────────────────────────────────────────────────────────────────

class _FakeJob:
    def __init__(self, job_id="j_stuck", status_val="stuck", lab="goad-light",
                 host="dc01", bolton_id="bolton.adcs.esc1", action_val="install",
                 log_path="/tmp/test-bolton.log", error_summary="verify probe failed"):
        self.id = job_id
        # Mimic JobStatus enum value attr.
        self.status = type("S", (), {"value": status_val})()
        self.lab = lab
        self.host = host
        self.bolton_id = bolton_id
        self.action = type("A", (), {"value": action_val})()
        self.log_path = log_path
        self.error_summary = error_summary


@pytest.fixture
def fake_services(monkeypatch, tmp_path):
    """Install fake install/facts/catalog services that bolton_agent_service
    imports lazily. Yields a dict for per-test configuration."""
    install_mod = types.ModuleType("webapp.backend.services.bolton_install_service")
    facts_mod = types.ModuleType("webapp.backend.services.bolton_facts_service")
    catalog_mod = types.ModuleType("webapp.backend.services.bolton_catalog_service")

    log_file = tmp_path / "job.log"
    log_file.write_text(
        "\n".join([f"line {i}: ansible output" for i in range(1, 250)]) + "\n"
    )

    job = _FakeJob(log_path=str(log_file))
    install_mod.get_job = MagicMock(return_value=job)
    facts_mod.get_cached_facts = MagicMock(return_value={
        "os_family": "windows", "role": "dc", "domain": "sevenkingdoms.local",
    })
    catalog_mod.get = MagicMock(return_value={
        "id": "bolton.adcs.esc1",
        "name": "ADCS ESC1",
        "category": "adcs",
        "inputs": {"template_name": {"type": "string"}, "force": {"type": "bool"}},
        "install": {"playbook": "install.yml"},
        "verify": {"command": "Get-CATemplate"},
    })

    monkeypatch.setitem(sys.modules, install_mod.__name__, install_mod)
    monkeypatch.setitem(sys.modules, facts_mod.__name__, facts_mod)
    monkeypatch.setitem(sys.modules, catalog_mod.__name__, catalog_mod)

    # Belt-and-braces: when test_bolton_routes' real_services fixture has
    # run earlier in the same session, the REAL install/facts/catalog
    # modules can still be sticky in Python's per-frame import resolution.
    # Patch the public functions on the real modules too, so agent code
    # that resolves via the real module (instead of sys.modules) sees
    # our fakes.
    try:
        from webapp.backend.services import bolton_install_service as _real_install
        monkeypatch.setattr(_real_install, "get_job", install_mod.get_job, raising=False)
    except ImportError:
        pass
    try:
        from webapp.backend.services import bolton_facts_service as _real_facts
        monkeypatch.setattr(_real_facts, "get_cached_facts", facts_mod.get_cached_facts, raising=False)
    except ImportError:
        pass
    try:
        from webapp.backend.services import bolton_catalog_service as _real_catalog
        monkeypatch.setattr(_real_catalog, "get", catalog_mod.get, raising=False)
    except ImportError:
        pass
    yield {
        "install": install_mod, "facts": facts_mod, "catalog": catalog_mod,
        "job": job, "log_file": log_file,
    }


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _final_proposal_response(diagnosis="template name conflict",
                             action="retry_with_inputs",
                             retry_inputs=None,
                             operator_question=None,
                             reasoning="rerun with force=true"):
    """Build a fake response whose text block contains the JSON proposal."""
    payload = {
        "diagnosis": diagnosis,
        "proposed_action": action,
        "retry_inputs": retry_inputs if retry_inputs is not None else {"force": True},
        "operator_question": operator_question,
        "reasoning": reasoning,
    }
    text = f"Analysis complete.\n\n```json\n{json.dumps(payload)}\n```\n"
    return _FakeResponse(content=[_Block(type="text", text=text)], stop_reason="end_turn")


def _tool_use_response(tool_name="check_service_status",
                      tool_input=None, tool_id="tu_a"):
    return _FakeResponse(
        content=[
            _Block(type="text", text="Let me check the service."),
            _Block(type="tool_use", id=tool_id, name=tool_name,
                   input=tool_input or {"service": "CertSvc"}),
        ],
        stop_reason="tool_use",
    )


# ──────────────────────────────────────────────────────────────────────
# Tests — API key + import handling
# ──────────────────────────────────────────────────────────────────────

def test_invoke_agent_raises_runtime_error_when_api_key_unset(monkeypatch):
    """Without ANTHROPIC_API_KEY, the agent service refuses to start."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    # Stop the install service stub from being imported eagerly — the
    # API key check happens FIRST so we never touch context building.
    from webapp.backend.services import bolton_agent_service
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        bolton_agent_service.invoke_agent("j_anything", "test-op")


def test_invoke_agent_raises_when_anthropic_sdk_missing(monkeypatch, env_api_key):
    """If anthropic isn't installed, fail fast with a clear error.

    We install a sentinel module that raises ImportError when accessed
    via the standard import machinery. The agent service does
    ``import anthropic`` inside ``invoke_agent`` (after the API-key
    check), so swapping the cached entry with a sentinel that raises
    on attribute access surfaces as ImportError → RuntimeError.
    """
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("no module named anthropic")
        return real_import(name, *args, **kwargs)

    monkeypatch.delitem(sys.modules, "anthropic", raising=False)
    monkeypatch.setattr(builtins, "__import__", fake_import)
    from webapp.backend.services import bolton_agent_service
    with pytest.raises(RuntimeError, match="anthropic SDK"):
        bolton_agent_service.invoke_agent("j_anything", "test-op")


# ──────────────────────────────────────────────────────────────────────
# Tests — context building + prompt structure
# ──────────────────────────────────────────────────────────────────────

def test_build_context_reads_log_tail_and_descriptor(env_api_key, fake_anthropic,
                                                     fake_services):
    from webapp.backend.services import bolton_agent_service
    ctx = bolton_agent_service._build_context("j_stuck")
    assert ctx.job_id == "j_stuck"
    assert ctx.lab == "goad-light"
    assert ctx.bolton_id == "bolton.adcs.esc1"
    # log_tail is the last 200 lines (we wrote 249 lines)
    line_count = ctx.log_tail.count("\n")
    assert line_count <= bolton_agent_service.MAX_LOG_TAIL_LINES
    assert line_count >= 100  # we wrote 249 lines so should hit the cap
    assert "ansible output" in ctx.log_tail
    # descriptor + facts both populated
    assert ctx.descriptor["id"] == "bolton.adcs.esc1"
    assert ctx.host_facts["os_family"] == "windows"


def test_build_context_rejects_non_stuck_job(env_api_key, fake_anthropic,
                                            fake_services):
    fake_services["job"].status = type("S", (), {"value": "running"})()
    from webapp.backend.services import bolton_agent_service
    with pytest.raises(ValueError, match="not 'stuck'"):
        bolton_agent_service._build_context("j_stuck")


def test_build_context_raises_keyerror_for_unknown_job(env_api_key,
                                                      fake_anthropic,
                                                      fake_services):
    fake_services["install"].get_job.return_value = None
    from webapp.backend.services import bolton_agent_service
    with pytest.raises(KeyError):
        bolton_agent_service._build_context("j_missing")


def test_system_prompt_mentions_hard_limits(env_api_key, fake_anthropic,
                                            fake_services):
    from webapp.backend.services import bolton_agent_service
    ctx = bolton_agent_service._build_context("j_stuck")
    prompt = bolton_agent_service._build_system_prompt(ctx)
    assert "3 tool invocations" in prompt or "3" in prompt
    assert "300 seconds" in prompt or "300" in prompt
    assert "READ-ONLY" in prompt
    assert "MUST NOT" in prompt
    assert "Set-*" in prompt


def test_user_message_includes_log_and_descriptor(env_api_key, fake_anthropic,
                                                  fake_services):
    from webapp.backend.services import bolton_agent_service
    ctx = bolton_agent_service._build_context("j_stuck")
    msg = bolton_agent_service._build_user_message(ctx)
    assert "Run log" in msg
    assert "Descriptor" in msg
    assert "Host facts" in msg
    assert "Recent audit slice" in msg


# ──────────────────────────────────────────────────────────────────────
# Tests — tool surface + dispatch
# ──────────────────────────────────────────────────────────────────────

def test_bounded_tools_are_readonly():
    """All declared tools must be read-only verbs (Get-*, certutil, klist, etc.)."""
    from webapp.backend.services import bolton_agent_service
    forbidden = ("Set-", "Remove-", "New-", "Stop-", "Restart-", "Disable-")
    for tool in bolton_agent_service._BOUNDED_TOOLS:
        name = tool["name"]
        dispatch = bolton_agent_service._TOOL_DISPATCH.get(name)
        assert dispatch is not None, f"tool {name} has no dispatch entry"
        _, template = dispatch
        for verb in forbidden:
            assert verb not in template, f"tool {name} contains forbidden verb {verb}"


def test_tool_dispatch_executes_known_tool(env_api_key, fake_anthropic,
                                          fake_services):
    from webapp.backend.services import bolton_agent_service
    out = bolton_agent_service._execute_tool(
        "check_service_status", {"service": "CertSvc"}, host="dc01"
    )
    assert out["ok"] is True
    assert "Get-Service" in out["command"]
    assert "CertSvc" in out["command"]
    assert out["host"] == "dc01"


def test_tool_dispatch_rejects_unknown_tool(env_api_key, fake_anthropic,
                                           fake_services):
    from webapp.backend.services import bolton_agent_service
    out = bolton_agent_service._execute_tool("rm_rf", {}, host="dc01")
    assert out["ok"] is False
    assert "unknown tool" in out["stderr"]


def test_tool_dispatch_event_log_caps_limit(env_api_key, fake_anthropic,
                                            fake_services):
    from webapp.backend.services import bolton_agent_service
    out = bolton_agent_service._execute_tool(
        "read_event_log", {"log_name": "System", "limit": 9999}, host="dc01"
    )
    assert out["ok"] is True
    # Cap is 200
    assert "-Newest 200" in out["command"]


# ──────────────────────────────────────────────────────────────────────
# Tests — invocation loop + hard limits
# ──────────────────────────────────────────────────────────────────────

def test_invoke_agent_happy_path_no_tools(env_api_key, fake_anthropic,
                                          fake_services):
    """Agent emits a final proposal immediately — no tool loop iteration."""
    from webapp.backend.services import bolton_agent_service

    captured_calls = []

    def _create(**kwargs):
        captured_calls.append(kwargs)
        return _final_proposal_response()

    fake_anthropic._create = _create

    # Replace client constructor so .messages.create uses our _create
    def _factory(*args, **kwargs):
        c = _FakeClient(*args, **kwargs)
        c.messages.create = _create
        return c

    with patch.object(sys.modules["anthropic"], "Anthropic", _factory):
        proposal = bolton_agent_service.invoke_agent("j_stuck", "test-op")

    assert proposal.proposed_action == "retry_with_inputs"
    assert proposal.retry_inputs == {"force": True}
    assert proposal.iterations_used == 1
    assert proposal.diagnostic_outputs == []
    assert len(captured_calls) == 1
    # Verify the API call carried the expected fields.
    assert captured_calls[0]["model"] == bolton_agent_service.DEFAULT_MODEL
    assert "tools" in captured_calls[0]
    assert len(captured_calls[0]["tools"]) >= 4
    assert "system" in captured_calls[0]


def test_invoke_agent_runs_one_tool_then_final_proposal(env_api_key,
                                                       fake_anthropic,
                                                       fake_services):
    """Agent makes 1 tool call → receives result → emits final proposal."""
    from webapp.backend.services import bolton_agent_service

    responses = iter([
        _tool_use_response(tool_name="check_service_status",
                          tool_input={"service": "CertSvc"}, tool_id="tu_1"),
        _final_proposal_response(),
    ])

    def _create(**_):
        return next(responses)

    def _factory(*args, **kwargs):
        c = _FakeClient(*args, **kwargs)
        c.messages.create = _create
        return c

    with patch.object(sys.modules["anthropic"], "Anthropic", _factory):
        proposal = bolton_agent_service.invoke_agent("j_stuck", "test-op")

    assert proposal.iterations_used == 2
    assert len(proposal.diagnostic_outputs) == 1
    assert proposal.diagnostic_outputs[0]["tool"] == "check_service_status"
    assert proposal.proposed_action == "retry_with_inputs"


def test_invoke_agent_enforces_tool_cap(env_api_key, fake_anthropic,
                                        fake_services):
    """Model keeps requesting tools — we hard-cap at MAX_TOOL_INVOCATIONS."""
    from webapp.backend.services import bolton_agent_service

    def _create(**_):
        # Always return a tool_use response. The loop must terminate
        # via the hard cap, not via the model's stop_reason.
        return _tool_use_response(
            tool_name="list_installed_kbs", tool_input={}, tool_id="tu_x"
        )

    def _factory(*args, **kwargs):
        c = _FakeClient(*args, **kwargs)
        c.messages.create = _create
        return c

    with patch.object(sys.modules["anthropic"], "Anthropic", _factory):
        proposal = bolton_agent_service.invoke_agent("j_stuck", "test-op")

    # Hard cap: exactly MAX_TOOL_INVOCATIONS diagnostic outputs.
    assert len(proposal.diagnostic_outputs) == bolton_agent_service.MAX_TOOL_INVOCATIONS
    # The proposal degrades to mark_failed when there's no JSON to parse.
    assert proposal.proposed_action == "mark_failed"


def test_invoke_agent_enforces_wall_clock_budget(env_api_key, fake_anthropic,
                                                 fake_services, monkeypatch):
    """If wall-clock exceeds MAX_WALL_CLOCK_SECONDS, we raise."""
    from webapp.backend.services import bolton_agent_service

    monkeypatch.setattr(bolton_agent_service, "MAX_WALL_CLOCK_SECONDS", 0.001)

    def _create(**_):
        time.sleep(0.01)  # blow the budget
        return _tool_use_response()

    def _factory(*args, **kwargs):
        c = _FakeClient(*args, **kwargs)
        c.messages.create = _create
        return c

    with patch.object(sys.modules["anthropic"], "Anthropic", _factory):
        with pytest.raises(RuntimeError, match="wall-clock"):
            bolton_agent_service.invoke_agent("j_stuck", "test-op")


# ──────────────────────────────────────────────────────────────────────
# Tests — retry_inputs validation
# ──────────────────────────────────────────────────────────────────────

def test_validate_retry_inputs_accepts_declared_keys():
    from webapp.backend.services import bolton_agent_service
    descriptor = {"inputs": {"template_name": {}, "force": {}}}
    ok, _ = bolton_agent_service._validate_retry_inputs(
        {"force": True}, descriptor
    )
    assert ok is True


def test_validate_retry_inputs_rejects_unknown_keys():
    from webapp.backend.services import bolton_agent_service
    descriptor = {"inputs": {"template_name": {}, "force": {}}}
    ok, reason = bolton_agent_service._validate_retry_inputs(
        {"some_nonexistent_key": "evil"}, descriptor
    )
    assert ok is False
    assert "unknown input keys" in reason


def test_invalid_retry_inputs_downgrades_to_mark_failed(env_api_key,
                                                       fake_anthropic,
                                                       fake_services):
    """Agent proposes retry with unknown input key → server downgrades."""
    from webapp.backend.services import bolton_agent_service

    def _create(**_):
        return _final_proposal_response(
            retry_inputs={"bogus_key_not_in_schema": 1},
            action="retry_with_inputs",
        )

    def _factory(*args, **kwargs):
        c = _FakeClient(*args, **kwargs)
        c.messages.create = _create
        return c

    with patch.object(sys.modules["anthropic"], "Anthropic", _factory):
        proposal = bolton_agent_service.invoke_agent("j_stuck", "test-op")

    assert proposal.proposed_action == "mark_failed"
    assert proposal.retry_inputs is None
    assert "downgraded" in proposal.reasoning


# ──────────────────────────────────────────────────────────────────────
# Tests — JSON parsing edge cases
# ──────────────────────────────────────────────────────────────────────

def test_parse_proposal_json_fenced_block():
    from webapp.backend.services import bolton_agent_service
    text = "intro\n```json\n{\"diagnosis\": \"ok\", \"proposed_action\": \"mark_failed\"}\n```\noutro"
    out = bolton_agent_service._parse_proposal_json(text)
    assert out["diagnosis"] == "ok"


def test_parse_proposal_json_fallback_bare_object():
    from webapp.backend.services import bolton_agent_service
    text = "thoughts\n\n{\"diagnosis\": \"raw\", \"proposed_action\": \"mark_failed\"}"
    out = bolton_agent_service._parse_proposal_json(text)
    assert out["diagnosis"] == "raw"


def test_parse_proposal_json_unparseable_returns_empty():
    from webapp.backend.services import bolton_agent_service
    out = bolton_agent_service._parse_proposal_json("just prose, no JSON here")
    assert out == {}


# ──────────────────────────────────────────────────────────────────────
# Tests — audit log emission
# ──────────────────────────────────────────────────────────────────────

def test_invoke_writes_audit_entries(env_api_key, fake_anthropic,
                                     fake_services, monkeypatch):
    """Invoke + per-tool calls all hit the audit log."""
    from webapp.backend.services import bolton_agent_service
    from webapp.backend.services import audit_service

    captured: list[dict] = []

    def _capture(op_id, action, *, target=None, project=None, details=None):
        captured.append({
            "op": op_id, "action": action, "target": target,
            "project": project, "details": details,
        })

    monkeypatch.setattr(audit_service, "write", _capture)

    responses = iter([
        _tool_use_response(tool_name="check_service_status",
                          tool_input={"service": "CertSvc"}),
        _final_proposal_response(),
    ])

    def _create(**_):
        return next(responses)

    def _factory(*args, **kwargs):
        c = _FakeClient(*args, **kwargs)
        c.messages.create = _create
        return c

    with patch.object(sys.modules["anthropic"], "Anthropic", _factory):
        bolton_agent_service.invoke_agent("j_stuck", "test-op")

    actions = [e["action"] for e in captured]
    assert "bolton.agent.invoke" in actions
    assert "bolton.agent.tool_call" in actions
    # Invoke entry includes the limit fields so future audit readers
    # can reconstruct what budget the run had.
    invoke = next(e for e in captured if e["action"] == "bolton.agent.invoke")
    assert invoke["details"]["limit_tool_calls"] == bolton_agent_service.MAX_TOOL_INVOCATIONS
    assert invoke["details"]["limit_wall_clock_s"] == bolton_agent_service.MAX_WALL_CLOCK_SECONDS


# ──────────────────────────────────────────────────────────────────────
# Tests — proposal_to_dict serialisation
# ──────────────────────────────────────────────────────────────────────

def test_proposal_to_dict_round_trip():
    from webapp.backend.services import bolton_agent_service
    p = bolton_agent_service.AgentProposal(
        diagnosis="ok",
        proposed_action="retry_with_inputs",
        retry_inputs={"force": True},
        operator_question=None,
        reasoning="evidence",
        diagnostic_outputs=[{"tool": "klist", "ok": True}],
        iterations_used=2,
        wall_clock_seconds=1.234,
    )
    d = bolton_agent_service.proposal_to_dict(p)
    assert d["diagnosis"] == "ok"
    assert d["proposed_action"] == "retry_with_inputs"
    assert d["retry_inputs"] == {"force": True}
    assert d["iterations_used"] == 2
    assert d["wall_clock_seconds"] == 1.234
    assert len(d["diagnostic_outputs"]) == 1


# ──────────────────────────────────────────────────────────────────────
# Tests — install service retry_with_modifications
# ──────────────────────────────────────────────────────────────────────

def test_retry_with_modifications_rejects_non_stuck_job(monkeypatch, tmp_path):
    """Only STUCK jobs can be retried via the agent path."""
    from webapp.backend.services import bolton_install_service as bis
    monkeypatch.setattr(bis, "JOBS_ROOT", tmp_path / "jobs")
    bis._reset_registry_for_tests()

    # Inject a SUCCEEDED job directly.
    job = bis.Job(
        id="j_done",
        action=bis.JobAction.INSTALL,
        bolton_id="bolton.test",
        lab="lab1",
        host="h1",
        operator="op",
        status=bis.JobStatus.SUCCEEDED,
    )
    with bis._JOBS_LOCK:
        bis._JOBS[job.id] = job

    with pytest.raises(ValueError, match="not 'stuck'"):
        bis.retry_with_modifications("j_done", {"x": 1})


def test_retry_with_modifications_keyerror_on_unknown(monkeypatch, tmp_path):
    from webapp.backend.services import bolton_install_service as bis
    monkeypatch.setattr(bis, "JOBS_ROOT", tmp_path / "jobs")
    bis._reset_registry_for_tests()
    with pytest.raises(KeyError):
        bis.retry_with_modifications("j_no_such", {"x": 1})
