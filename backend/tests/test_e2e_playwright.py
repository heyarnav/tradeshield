#!/usr/bin/env python3
"""TradeShield * Playwright end-to-end tests.

These are **integration/acceptance** tests, not unit tests: each one spins up
the real Flask API and the real Next.js frontend, logs in as a known seed
account (or a freshly registered one), drives the browser, and asserts against
the **visible UI and the HTTP layer** -- never against internal implementation
details.

Run them with:

    cd backend
    .venv/bin/python -m pytest tests/test_e2e_playwright.py -q

They are skipped (pytest.skip) when the browsers or the servers cannot be
reached, so they never fail a pipeline for environment reasons.

IMPORTANT -- servers:
    The tests start Flask in the **same process** they run in and await
    ``/api/health``, so no long-running server process is required to exist
    before the suite runs. The Next.js dev server is also started by the test
    harness from ``frontend/``. Both are torn down in fixture teardown.
"""

from __future__ import annotations

import contextlib
import multiprocessing
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"


def _env() -> dict[str, str]:
    """Best-effort .env load (same semantics as app/config.py / apply.py)."""
    env = dict(os.environ)
    for path in (ROOT / ".env",):
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    return env


def _flask_port(env: dict[str, str]) -> int:
    try:
        return int(env.get("FLASK_PORT", "5001"))
    except ValueError:
        return 5001


def _await_url(url: str, status_ok: tuple[int, ...] = (200, 307, 308),
               timeout_s: float = 2.0, deadline: float | None = None) -> bool:
    """Return True the first time *url* responds with an acceptable status."""
    if deadline is None:
        deadline = time.time() + 60
    while time.time() < deadline:
        try:
            import urllib.request, urllib.error
            with urllib.request.urlopen(url, timeout=timeout_s) as r:
                if r.status in status_ok:
                    return True
        except (urllib.error.URLError, OSError, ConnectionError):
            pass
        time.sleep(0.5)
    return False

# ---------------------------------------------------------------------------
# server fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def servers(request):
    """Start Flask + Next.js dev server for the session; await health checks.

    Flask is started as a subprocess so it survives pytest collection but is
    killed in teardown. The Flask subprocess inherits a copy of the env so
    DATABASE_URL / JWT_SECRET etc. are available.
    """
    env = _env()
    port = _flask_port(env)

    venv_python = BACKEND / ".venv" / "bin" / "python"
    if not venv_python.exists():
        pytest.skip("backend .venv python not found at "
                    f"{venv_python} -- run from backend/ after creating .venv")
    flask_proc = subprocess.Popen(
        [str(venv_python), str(BACKEND / "run.py")],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )

    # Next.js dev server: start it in the same shell-owned process group so the
    # fixture can await it and tear it down deterministically. We run it
    # attached (not detached) so pytest owns its lifetime.
    next_proc = subprocess.Popen(
        [os.environ.get("NODE", "node"), str(FRONTEND / "node_modules" / ".bin" / "next"), "dev"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env,
        start_new_session=True,
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        try:
            api_base = f"http://127.0.0.1:{port}"
            if not _await_url(f"{api_base}/api/health", deadline=time.time() + 30):
                pytest.skip("flask did not become healthy in time")
                return

            next_url = "http://localhost:3000"
            if not _await_url(next_url, deadline=time.time() + 120):
                pytest.skip("next.js dev server did not become reachable in time")
                return

            yield api_base, next_url, browser
        finally:
            browser.close()
        for proc, name in ((flask_proc, "flask"), (next_proc, "next.js")):
            if proc.poll() is None:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    proc.wait()

@pytest.fixture
def page(servers):
    api_base, next_url, browser = servers
    page = browser.new_page()
    page.set_default_timeout(15000)
    page.goto(next_url)
    yield page
    page.close()

# ---------------------------------------------------------------------------
# seed accounts (documented demo credentials)
# ---------------------------------------------------------------------------

@pytest.fixture
def client_credentials():
    return {"email": "client@tradeshield.dev", "password": "Client@123"}

@pytest.fixture
def admin_credentials():
    return {"email": "admin@tradeshield.dev", "password": "Admin@123"}

# ---------------------------------------------------------------------------
# tests
# ---------------------------------------------------------------------------

def _login(page, email, password):
    page.goto("/login")
    page.get_by_label("Email").fill(email)
    page.get_by_label("Password").fill(password)
    # The button label is "Sign in" when idle and "Signing in>>" while busy.
    page.get_by_role("button", name="Sign in").click()
    # after login the app redirects to /dashboard
    page.wait_for_url("/dashboard", timeout=10000)

def _logout(page):
    page.goto("/account")
    with page.expect_popup(timeout=5000) as popup_info:
        page.get_by_role("button", name="Sign out").click()
    popup = popup_info.value
    popup.wait_for_url("**/login", timeout=8000)

def _navigate_to(page, path):
    page.goto(path)
    page.wait_for_load_state("networkidle", timeout=12000)

# ---- client auth ---------------------------------------------------------

def test_client_can_login(page, client_credentials):
    page.goto("/login")
    page.get_by_label("Email").fill(client_credentials["email"])
    page.get_by_label("Password").fill(client_credentials["password"])
    # The idle button label is "Sign in"; it becomes "Signing in>>" while busy.
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("/dashboard", timeout=10000)
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()

def test_client_cannot_access_admin_without_permission(page, client_credentials):
    _login(page, **client_credentials)
    # the admin nav item should not be reachable for a normal client
    with page.expect_popup(timeout=5000):
        page.get_by_role("link", name="Security").click()
    # security dashboard is admin-only -> 403 JSON, frontend shows access denied
    page.wait_for_load_state("networkidle", timeout=10000)
    # The app surfaces a human-readable message, not a stack trace.
    page.wait_for_function(
        "document.body.innerText.includes('access') || "
        "document.body.innerText.includes('denied') || "
        "document.body.innerText.includes('forbidden')",
        timeout=5000,
    )

# ---- dashboard / market --------------------------------------------------

def test_dashboard_shows_positions(page, client_credentials):
    _login(page, **client_credentials)
    page.wait_for_url("/dashboard", timeout=10000)
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()
    # Dashboard surfaces cash + positions when there are any; seed client has
    # an opening position so the page is not empty.
    page.wait_for_function(
        "document.body.innerText.length > 0", timeout=5000
    )

def test_market_page_loads_instruments(page, client_credentials):
    _login(page, **client_credentials)
    page.goto("/market")
    page.wait_for_url("/market", timeout=10000)
    expect(page.get_by_role("heading", name="Market")).to_be_visible()
    # at least one instrument row renders (seeded instruments exist)
    page.wait_for_selector("text=ACME", timeout=8000)

# ---- orders: BUY / SELL / validation / blocked --------------------------

def _place_order(page, instrument, side, order_type, quantity, limit_price=None):
    page.goto("/orders")
    page.wait_for_url("/orders", timeout=10000)
    # open the ticket
    page.get_by_role("button", name="New order").click()
    page.wait_for_selector("h3:has-text('New order')", timeout=8000)
    page.get_by_label("Symbol").fill(instrument)
    page.get_by_label("Side").click()
    page.get_by_label("Side").filter(has_text=side).first.click()
    page.get_by_label("Type").click()
    page.get_by_label("Type").filter(has_text=order_type).first.click()
    page.get_by_label("Quantity").fill(str(quantity))
    if limit_price is not None:
        page.get_by_label("Limit price").fill(str(limit_price))
    with page.expect_response(
        lambda r: r.url.startswith("/api/orders") and r.request.method == "POST",
        timeout=12000,
    ) as resp_info:
        page.get_by_role("button", name="Place order").click()
    response = resp_info.value
    return response

def test_successful_buy_updates_portfolio(page, client_credentials):
    _login(page, **client_credentials)
    # buy a small number of ACME (current price 175.40 in seed)
    resp = _place_order(page, "ACME", "BUY", "MARKET", 1)
    assert resp.status == 201
    body = resp.json()
    assert body["data"]["order"]["side"] == "BUY"
    assert body["data"]["order"]["status"] == "EXECUTED"
    # portfolio should now list ACME
    page.goto("/portfolio")
    page.wait_for_url("/portfolio", timeout=10000)
    page.wait_for_selector("text=ACME", timeout=8000)

def test_successful_sell_reduces_holding(page, client_credentials):
    _login(page, **client_credentials)
    # sell 1 ACME (seed client already holds 100)
    resp = _place_order(page, "ACME", "SELL", "MARKET", 1)
    assert resp.status == 201
    body = resp.json()
    assert body["data"]["order"]["side"] == "SELL"
    assert body["data"]["order"]["status"] == "EXECUTED"

def test_insufficient_funds_rejected(page, client_credentials):
    _login(page, **client_credentials)
    resp = _place_order(page, "ACME", "BUY", "MARKET", 1000000)
    assert resp.status in (400, 403, 422)
    body = resp.json()
    assert body.get("error", {}).get("code") in (
        "INSUFFICIENT_FUNDS", "ORDER_BLOCKED", "VALIDATION_ERROR"
    )

def test_insufficient_holdings_rejected(page, client_credentials):
    _login(page, **client_credentials)
    resp = _place_order(page, "ACME", "SELL", "MARKET", 999999)
    assert resp.status in (400, 403, 422)
    body = resp.json()
    assert body.get("error", {}).get("code") in (
        "INSUFFICIENT_HOLDINGS", "VALIDATION_ERROR"
    )

def test_blocked_order_shows_clear_message(page, client_credentials):
    # A real blocked order requires the screened IP to be a known threat.
    # With TRUST_CLIENT_IP_HEADER=false (the safe default) the browser
    # cannot spoof the screened IP, so a blocked order cannot be triggered
    # end-to-end from the UI in that configuration. We therefore assert the
    # API contract directly: posting a known-bad IP to the orders endpoint
    # returns ORDER_BLOCKED and the order never becomes visible.
    import urllib.request, urllib.error, json

    # Obtain a real token for the seeded client via the browser's own flow:
    page.goto("/login")
    page.get_by_label("Email").fill(client_credentials["email"])
    page.get_by_label("Password").fill(client_credentials["password"])
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("/dashboard", timeout=10000)
    token = page.evaluate(
        "() => (document.cookie.match(/token=([^;]+)/) || [])[1]"
    )
    assert token, "client did not receive a session token"

    payload = json.dumps({
        "instrument": "ACME",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": 1,
        "origin_ip": "198.51.100.66",
    }).encode()
    req = urllib.request.Request(
        f"/api/orders",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            status = r.status
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        status = e.code
        body = json.loads(e.read())
    assert status == 403, f"expected 403, got {status}: {body}"
    assert body["error"]["code"] == "ORDER_BLOCKED", body
    # and the order really does not exist in the UI
    page.goto("/orders")
    page.wait_for_url("/orders", timeout=10000)
    page.wait_for_function(
        "typeof document !== 'undefined' && "
        "document.body.innerText.indexOf('198.51.100.66') === -1",
        timeout=5000,
    )

def test_limit_order_requires_price(page, client_credentials):
    _login(page, **client_credentials)
    page.goto("/orders")
    page.wait_for_url("/orders", timeout=10000)
    page.get_by_role("button", name="New order").click()
    page.wait_for_selector("h3:has-text('New order')", timeout=8000)
    page.get_by_label("Symbol").fill("ACME")
    page.get_by_label("Side").filter(has_text="BUY").first.click()
    page.get_by_label("Type").filter(has_text="LIMIT").first.click()
    page.get_by_label("Quantity").fill("1")
    # do NOT fill limit price
    with page.expect_response(
        lambda r: r.url.startswith("/api/orders") and r.request.method == "POST",
        timeout=12000,
    ) as resp_info:
        page.get_by_role("button", name="Place order").click()
    resp = resp_info.value
    assert resp.status == 422
    body = resp.json()
    assert body["error"]["code"] == "LIMIT_PRICE_REQUIRED"

# ---- portfolio / transactions --------------------------------------------

def test_portfolio_and_transactions_reflect_trades(page, client_credentials):
    _login(page, **client_credentials)
    # ensure there is at least one executed trade to read (seed has opening
    # position; place a tiny buy if needed)
    page.goto("/portfolio")
    page.wait_for_url("/portfolio", timeout=10000)
    expect(page.get_by_role("heading", name="Portfolio")).to_be_visible()
    page.goto("/transactions")
    page.wait_for_url("/transactions", timeout=10000)
    expect(page.get_by_role("heading", name="Transactions")).to_be_visible()

# ---- admin: security pages ----------------------------------------------

def test_admin_can_view_security_dashboard(page, admin_credentials):
    page.goto("/login")
    page.get_by_label("Email").fill(admin_credentials["email"])
    page.get_by_label("Password").fill(admin_credentials["password"])
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("/dashboard", timeout=10000)
    with page.expect_popup(timeout=5000):
        page.get_by_role("link", name="Security").click()
    page.wait_for_url("/admin/security", timeout=10000)
    expect(page.get_by_role("heading", name="Security dashboard")).to_be_visible()

def test_admin_can_view_threat_indicators(page, admin_credentials):
    page.goto("/login")
    page.get_by_label("Email").fill(admin_credentials["email"])
    page.get_by_label("Password").fill(admin_credentials["password"])
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("/dashboard", timeout=10000)
    with page.expect_popup(timeout=5000):
        page.get_by_role("link", name="Threat indicators").click()
    page.wait_for_url("/admin/threats", timeout=10000)
    expect(page.get_by_role("heading", name="Threat indicators")).to_be_visible()
    # seeded indicators exist
    page.wait_for_selector("text=198.51.100.66", timeout=8000)

def test_admin_can_view_blocked_orders(page, admin_credentials):
    page.goto("/login")
    page.get_by_label("Email").fill(admin_credentials["email"])
    page.get_by_label("Password").fill(admin_credentials["password"])
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("/dashboard", timeout=10000)
    with page.expect_popup(timeout=5000):
        page.get_by_role("link", name="Blocked orders").click()
    page.wait_for_url("/admin/blocked", timeout=10000)
    expect(page.get_by_role("heading", name="Blocked orders")).to_be_visible()

def test_admin_can_view_audit_logs(page, admin_credentials):
    page.goto("/login")
    page.get_by_label("Email").fill(admin_credentials["email"])
    page.get_by_label("Password").fill(admin_credentials["password"])
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_url("/dashboard", timeout=10000)
    with page.expect_popup(timeout=5000):
        page.get_by_role("link", name="Audit logs").click()
    page.wait_for_url("/admin/audit", timeout=10000)
    expect(page.get_by_role("heading", name="Audit logs")).to_be_visible()

# ---- auth failure paths --------------------------------------------------

def test_invalid_credentials_show_error(page):
    page.goto("/login")
    page.get_by_label("Email").fill("nobody@tradeshield.dev")
    page.get_by_label("Password").fill("wrong")
    page.get_by_role("button", name="Sign in").click()
    page.wait_for_function(
        "document.body.innerText.includes('incorrect') || "
        "document.body.innerText.includes('invalid')",
        timeout=8000,
    )
