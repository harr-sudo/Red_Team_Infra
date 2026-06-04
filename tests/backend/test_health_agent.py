"""task #52 — /api/health/agent endpoint contract tests.

Surfaces ANTHROPIC_API_KEY + anthropic SDK presence for the bolt-on
agentic fallback. Operators see the status proactively in Settings →
Prereqs instead of discovering it via a 503 on Invoke Agent.

Hard constraint: the endpoint MUST NEVER return the actual API key
value. These tests assert that explicitly — every other surface in this
code base reads the env var (audit, agent service, etc.) but only this
endpoint is exposed to the frontend.
"""
import json
import sys
import builtins
import importlib

import pytest


def _get_json(client):
    response = client.get('/api/health/agent')
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    data = response.get_json()
    assert data is not None, "Expected JSON body"
    assert data.get('success') is True
    return data


# ─────────────────────────────────────────────────────────────────────────
# Configured-state mirrors env var presence
# ─────────────────────────────────────────────────────────────────────────

def test_configured_true_when_env_var_set(flask_client, monkeypatch):
    """When ANTHROPIC_API_KEY is set, configured=True + key_source=env."""
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-test-fake-value-12345')
    data = _get_json(flask_client)
    assert data['configured'] is True
    assert data['key_source'] == 'env'


def test_configured_false_when_env_var_unset(flask_client, monkeypatch):
    """When ANTHROPIC_API_KEY is absent, configured=False + key_source=none."""
    monkeypatch.delenv('ANTHROPIC_API_KEY', raising=False)
    data = _get_json(flask_client)
    assert data['configured'] is False
    assert data['key_source'] == 'none'


def test_configured_false_when_env_var_empty_string(flask_client, monkeypatch):
    """Empty string is treated the same as unset — bool('') == False."""
    monkeypatch.setenv('ANTHROPIC_API_KEY', '')
    data = _get_json(flask_client)
    assert data['configured'] is False
    assert data['key_source'] == 'none'


# ─────────────────────────────────────────────────────────────────────────
# Model name: env override + sensible default
# ─────────────────────────────────────────────────────────────────────────

def test_model_defaults_when_env_unset(flask_client, monkeypatch):
    """BOLTON_AGENT_MODEL unset → fallback to documented default."""
    monkeypatch.delenv('BOLTON_AGENT_MODEL', raising=False)
    data = _get_json(flask_client)
    assert data['model'] == 'claude-sonnet-4-6'


def test_model_uses_env_override(flask_client, monkeypatch):
    """BOLTON_AGENT_MODEL is reflected verbatim in the response."""
    monkeypatch.setenv('BOLTON_AGENT_MODEL', 'claude-haiku-3-5-20241022')
    data = _get_json(flask_client)
    assert data['model'] == 'claude-haiku-3-5-20241022'


# ─────────────────────────────────────────────────────────────────────────
# anthropic_sdk_installed reflects actual import availability
# ─────────────────────────────────────────────────────────────────────────

def test_anthropic_sdk_installed_reflects_import(flask_client):
    """The flag must reflect actual import availability of the anthropic SDK.

    We can't reliably control whether the SDK is installed in the test
    venv — but we CAN verify the response matches the real probe result
    by doing the same import check ourselves and comparing.
    """
    data = _get_json(flask_client)
    try:
        import anthropic  # noqa: F401
        actual = True
    except ImportError:
        actual = False
    assert data['anthropic_sdk_installed'] is actual


# ─────────────────────────────────────────────────────────────────────────
# Hard security constraint: NEVER return the API key value
# ─────────────────────────────────────────────────────────────────────────

def test_response_never_contains_api_key_value(flask_client, monkeypatch):
    """Even with the key set, the response body must not embed the key.

    This is the load-bearing assertion for this task — the endpoint
    surfaces presence, never the secret material. Regression here would
    leak the key to anyone who can reach the dashboard.
    """
    fake_key = 'sk-ant-load-bearing-secret-DO-NOT-LEAK-9876543210'
    monkeypatch.setenv('ANTHROPIC_API_KEY', fake_key)
    response = flask_client.get('/api/health/agent')
    raw = response.get_data(as_text=True)
    assert fake_key not in raw, (
        "API key value was returned in the response body — this is a "
        "secret-disclosure regression. The endpoint must only report "
        "presence (configured: bool), never the key itself."
    )
    # Also assert no field shaped like an api key
    data = response.get_json()
    for k, v in data.items():
        if isinstance(v, str):
            assert not v.startswith('sk-ant-'), f"Field '{k}' looks like an API key"


def test_response_shape_is_documented_contract(flask_client, monkeypatch):
    """The response shape must match the documented contract — frontend
    code in app.js (loadSettingsAgentCheck, _gateInvokeAgentButton) keys
    off these exact field names."""
    monkeypatch.setenv('ANTHROPIC_API_KEY', 'sk-ant-test')
    data = _get_json(flask_client)
    required_keys = {'success', 'configured', 'model', 'key_source', 'anthropic_sdk_installed'}
    assert required_keys.issubset(set(data.keys())), (
        f"Missing required keys. Got: {set(data.keys())}, want superset of: {required_keys}"
    )
    assert isinstance(data['configured'], bool)
    assert isinstance(data['anthropic_sdk_installed'], bool)
    assert isinstance(data['model'], str)
    assert data['key_source'] in ('env', 'secrets-manager', 'none')
