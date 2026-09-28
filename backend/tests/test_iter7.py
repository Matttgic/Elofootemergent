"""Iteration 7: goals recalibration, /api/stats, removal of /api/admin/ingest."""
import statistics
import pytest
import requests

from backend_url import API

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def s():
    sess = requests.Session()
    sess.headers.update({"Content-Type": "application/json"})
    return sess


# --- Admin ingest endpoint removed ---
def test_admin_ingest_removed(s):
    r = s.post(f"{API}/admin/ingest", timeout=30)
    assert r.status_code == 404


def test_status_still_works(s):
    r = s.get(f"{API}/status", timeout=30)
    assert r.status_code == 200
    d = r.json()
    for k in ("derniere_synchro", "synchronisation_en_cours", "frequence"):
        assert k in d


# --- Goals estimation variety (Poisson calibration) ---
def _sample_match_ids(s, code, limit=30):
    dates = s.get(f"{API}/dates?code={code}", timeout=30).json()
    ids = []
    # sample dates spread through the season
    step = max(1, len(dates) // 10)
    for d in dates[::step]:
        r = s.get(f"{API}/matches?code={code}&date={d}", timeout=60).json()
        for m in r.get("matchs", []):
            ids.append(m["match_id"])
            if len(ids) >= limit:
                return ids
    return ids


def test_goals_estimated_vary_across_matches(s):
    ids = _sample_match_ids(s, "PL", limit=25)
    assert len(ids) >= 10, f"Not enough sample matches: {len(ids)}"
    totals = []
    statuts = set()
    for mid in ids:
        r = s.get(f"{API}/match/{mid}", timeout=60)
        if r.status_code != 200:
            continue
        sig = r.json().get("signaux") or {}
        if not sig.get("disponible"):
            continue
        be = sig.get("buts_estimes") or {}
        tot = be.get("total")
        if tot is not None:
            totals.append(tot)
        for s_ in sig.get("signaux", []):
            if s_.get("marche", "").lower().startswith("plus de 2.5"):
                statuts.add(s_.get("statut"))
    assert len(totals) >= 8, f"Not enough usable signals: {len(totals)}"
    mean = statistics.mean(totals)
    stdev = statistics.pstdev(totals)
    mn, mx = min(totals), max(totals)
    print(f"Totals sample n={len(totals)} mean={mean:.2f} stdev={stdev:.2f} min={mn:.2f} max={mx:.2f}")
    print(f"Statuts Over 2.5: {statuts}")
    # Mean around realistic football scoring
    assert 1.8 <= mean <= 3.2, f"Mean total {mean} not in [1.8,3.2]"
    # Should have variation, not stuck ~3
    assert stdev >= 0.25, f"Stdev too low ({stdev}), totals look constant"
    assert (mx - mn) >= 0.8, f"Range too small ({mn}..{mx})"
    # And multiple statuses on Over 2.5
    assert len(statuts) >= 2, f"Only one statut seen on Over 2.5: {statuts}"


# --- /api/stats ---
def test_stats_global(s):
    r = s.get(f"{API}/stats", timeout=180)
    assert r.status_code == 200
    d = r.json()
    assert d["disponible"] is True
    assert d["echantillon"] > 0
    ns = d["note_superieure"]
    for k in ("victoires_pct", "nuls_pct", "defaites_pct"):
        assert k in ns
        assert ns[k] is None or 0 <= ns[k] <= 100
    ah = d["avantage_domicile"]
    for k in ("domicile_pct", "nul_pct", "exterieur_pct"):
        assert k in ah
        assert 0 <= ah[k] <= 100
    par = d["par_ecart_note"]
    labels = [b["tranche"] for b in par]
    assert labels == ["0–5", "5–10", "10–15", "15–20", "20–25", "25–30", "30–35", "35–40", "40–45", "45–50", "50+"]
    for b in par:
        for k in ("matchs", "note_sup_gagne_pct", "nul_pct", "note_inf_gagne_pct"):
            assert k in b
    # Monotonicity: higher gap => note_sup_gagne_pct trends upward (allow noise)
    pcts = [b["note_sup_gagne_pct"] for b in par if b["matchs"] >= 5 and b["note_sup_gagne_pct"] is not None]
    assert len(pcts) >= 3
    # First bucket win% should be lower than last bucket win%
    print("note_sup pct by bucket (matchs>=5):", pcts)
    assert pcts[0] < pcts[-1], f"Not monotonic: {pcts}"


def test_stats_pl_only(s):
    r = s.get(f"{API}/stats?code=PL", timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert d["disponible"] is True
    assert d["echantillon"] > 0
