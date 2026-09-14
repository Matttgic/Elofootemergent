"""Tests for the auto-update / manual refresh mechanism."""
import os
import time
import pytest
import requests

BASE_URL = ""
try:
    with open('/app/frontend/.env') as f:
        for line in f:
            if line.startswith('REACT_APP_BACKEND_URL='):
                BASE_URL = line.split('=', 1)[1].strip().rstrip('/')
except Exception:
    pass
if not BASE_URL:
    BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001').rstrip('/')

API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    return requests.Session()


def test_status_has_new_fields(s):
    r = s.get(f"{API}/status", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "synchronisation_en_cours" in d
    assert isinstance(d["synchronisation_en_cours"], bool)
    assert "frequence" in d
    assert "2 heures" in d["frequence"]
    assert d["matchs_en_base"] > 0
    sync = d.get("derniere_synchro") or {}
    assert "last_sync" in sync, f"missing last_sync in derniere_synchro: {sync}"


def test_admin_ingest_non_blocking_and_guard(s):
    # Capture previous last_sync
    st0 = s.get(f"{API}/status", timeout=30).json()
    prev_last = (st0.get("derniere_synchro") or {}).get("last_sync")

    t0 = time.time()
    r1 = s.post(f"{API}/admin/ingest", timeout=15)
    elapsed = time.time() - t0
    assert r1.status_code == 200
    body1 = r1.json()
    assert "started" in body1
    # Must respond quickly (non-blocking)
    assert elapsed < 10, f"POST /admin/ingest took {elapsed:.1f}s (should be immediate)"

    # If not started, it must be because a sync is already running
    if not body1["started"]:
        assert body1.get("raison") == "deja_en_cours"

    # A second immediate call should return started:false / deja_en_cours
    r2 = s.post(f"{API}/admin/ingest", timeout=15)
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2.get("started") is False
    assert body2.get("raison") == "deja_en_cours"

    # Poll status: synchronisation_en_cours should become true quickly (or already true)
    running_seen = False
    for _ in range(6):
        st = s.get(f"{API}/status", timeout=30).json()
        if st.get("synchronisation_en_cours"):
            running_seen = True
            break
        time.sleep(1)
    assert running_seen, "synchronisation_en_cours never became True after POST /admin/ingest"

    # Wait for completion (up to ~150s)
    completed = False
    new_last = None
    for _ in range(30):
        time.sleep(5)
        st = s.get(f"{API}/status", timeout=30).json()
        if not st.get("synchronisation_en_cours"):
            completed = True
            new_last = (st.get("derniere_synchro") or {}).get("last_sync")
            break
    assert completed, "sync did not finish within ~150s"
    assert new_last, "last_sync missing after sync"
    if prev_last:
        assert new_last >= prev_last, f"last_sync not updated: {prev_last} -> {new_last}"


# ---- quick regression
def test_matches_ok(s):
    r = s.get(f"{API}/matches", timeout=60)
    assert r.status_code == 200
    assert "matchs" in r.json()


def test_match_detail_ok(s):
    r = s.get(f"{API}/match/558894", timeout=60)
    assert r.status_code == 200


def test_leaderboard_teams_ok(s):
    r = s.get(f"{API}/leaderboard/teams?code=PL", timeout=60)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_leaderboard_players_ok(s):
    r = s.get(f"{API}/leaderboard/players?code=PL", timeout=60)
    assert r.status_code == 200
    assert r.json().get("disponible") is True


def test_players_form_ok(s):
    r = s.post(f"{API}/players/form", json={"ids": ["8026"]}, timeout=120)
    assert r.status_code == 200
