"""Tests for pipeline runtime modes and environment guards."""
from __future__ import annotations

import os
import pytest
from bet.pipeline.core_integration_contracts import live_integrations_allowed
from bet.pipeline.runtime_modes import RuntimeMode, validate_runtime_mode_acks, LIVE_ACK_KEY, LIVE_ACK_VALUE, WRITE_ACK_KEY, WRITE_ACK_VALUE


def test_runtime_modes_enum():
    assert RuntimeMode.CERTIFICATION == "CERTIFICATION"
    assert RuntimeMode.DRY_RUN == "DRY_RUN"
    assert RuntimeMode.LIVE_SHADOW == "LIVE_SHADOW"
    assert RuntimeMode.PRODUCTION == "PRODUCTION"


def test_validate_runtime_mode_acks_dry_run():
    # DRY_RUN requires no explicit env acks
    is_valid, err = validate_runtime_mode_acks(RuntimeMode.DRY_RUN)
    assert is_valid is True
    assert err == ""


def test_validate_runtime_mode_acks_live_shadow(monkeypatch):
    monkeypatch.delenv(LIVE_ACK_KEY, raising=False)
    is_valid, err = validate_runtime_mode_acks(RuntimeMode.LIVE_SHADOW)
    assert is_valid is False
    assert err == "BLOCKED_LIVE_NETWORK_ACK_MISSING"

    monkeypatch.setenv(LIVE_ACK_KEY, LIVE_ACK_VALUE)
    is_valid, err = validate_runtime_mode_acks(RuntimeMode.LIVE_SHADOW)
    assert is_valid is True
    assert err == ""


def test_validate_runtime_mode_acks_production(monkeypatch):
    monkeypatch.delenv(WRITE_ACK_KEY, raising=False)
    is_valid, err = validate_runtime_mode_acks(RuntimeMode.PRODUCTION)
    assert is_valid is False
    assert err == "BLOCKED_WRITE_ACK_MISSING"

    monkeypatch.setenv(WRITE_ACK_KEY, WRITE_ACK_VALUE)
    is_valid, err = validate_runtime_mode_acks(RuntimeMode.PRODUCTION)
    assert is_valid is True
    assert err == ""


def test_live_integrations_allowed_requires_ack_for_runtime_managed_env():
    allowed, reason = live_integrations_allowed("S2", environ={"BET_PIPELINE_RUNTIME_MODE": "DRY_RUN"})
    assert allowed is False
    assert reason == "BLOCKED_LIVE_NETWORK_ACK_MISSING"

    allowed, reason = live_integrations_allowed(
        "S4",
        environ={
            "BET_PIPELINE_RUNTIME_MODE": "LIVE_SHADOW",
            LIVE_ACK_KEY: LIVE_ACK_VALUE,
        },
    )
    assert allowed is True
    assert reason == ""
