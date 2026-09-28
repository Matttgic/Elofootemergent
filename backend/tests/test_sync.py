"""Tests for the light-refresh / manual refresh mechanism (économique)."""
import time
import pytest
import requests

from backend_url import API

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def s():
    return requests.Session()


def test_status_exposes_frequence_and_quota(s):
    r = s.get(f"{API}/status", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert "synchronisation_en_cours" in d
    assert isinstance(d["synchronisation_en_cours"], bool)
    assert "frequence" in d
    freq = d["frequence"]
    # New wording: "1 appel API" per hour + "analyse complète 1×/jour"
    assert "1 appel API" in freq
    assert "1×/jour" in freq or "1x/jour" in freq
    assert "quota" in d
    assert d["matchs_en_base"] > 0
    sync = d.get("derniere_synchro") or {}
    assert "last_sync" in sync


def test_admin_ingest_light_non_blocking_and_guard(s):
    # If a sync is currently running, wait briefly for it to end so we own this test.
    for _ in range(30):
        st = s.get(f"{API}/status", timeout=30).json()
        if not st.get("synchronisation_en_cours"):
            break
        time.sleep(2)

    st0 = s.get(f"{API}/status", timeout=30).json()
    prev_last = (st0.get("derniere_synchro") or {}).get("last_sync")

    t0 = time.time()
    r1 = s.post(f"{API}/admin/ingest", timeout=15)
    elapsed = time.time() - t0
    assert r1.status_code == 200
    body1 = r1.json()
    assert "started" in body1
    assert elapsed < 5, f"POST /admin/ingest took {elapsed:.1f}s (should be <5s)"
    assert body1.get("started") is True, f"expected started:true, got {body1}"

    # Immediate second call => started:false / raison:deja_en_cours
    r2 = s.post(f"{API}/admin/ingest", timeout=15)
    assert r2.status_code == 200
    body2 = r2.json()
    assert body2.get("started") is False
    assert body2.get("raison") == "deja_en_cours"

    # Light refresh should complete quickly (few seconds, not 90s).
    completed = False
    new_sync = None
    deadline = time.time() + 45
    while time.time() < deadline:
        time.sleep(2)
        st = s.get(f"{API}/status", timeout=30).json()
        if not st.get("synchronisation_en_cours"):
            new_sync = st.get("derniere_synchro") or {}
            completed = True
            break
    assert completed, "light sync did not finish within 45s"
    assert new_sync.get("last_sync"), "last_sync missing after sync"
    if prev_last:
        assert new_sync["last_sync"] >= prev_last
    # Mode should be "leger" and matchs_maj should be present (>=0, often >0)
    assert new_sync.get("mode") == "leger", f"expected mode=leger, got {new_sync}"
    assert "matchs_maj" in new_sync
    assert isinstance(new_sync["matchs_maj"], int)


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


def test_scoring_config_ok(s):
    r = s.get(f"{API}/scoring/config", timeout=30)
    assert r.status_code == 200
