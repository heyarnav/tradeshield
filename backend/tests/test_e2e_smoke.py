#!/usr/bin/env python3
"""Smoke test for the e2e fixture: proves the fixture can start/stop servers."""
from __future__ import annotations
import pytest
from playwright.sync_api import sync_playwright

def test_fixture_starts_servers(servers):
    # If we got here, the fixture already started flask + next and awaited health.
    api_base, next_url, browser = servers
    assert api_base.startswith("http://127.0.0.1:")
    assert next_url == "http://localhost:3000"
    assert browser is not None
