"""URL du backend déployé, pour les tests d'intégration (marqueur `integration`).

Priorité : variable d'environnement REACT_APP_BACKEND_URL, puis /app/frontend/.env
(pod Emergent). Sans URL, conftest.py ignore ces tests au lieu d'appeler une
adresse codée en dur.
"""
import os


def _from_frontend_env(path="/app/frontend/.env"):
    try:
        with open(path) as f:
            for line in f:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip()
    except OSError:
        pass
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _from_frontend_env() or "").rstrip("/")
API = f"{BASE_URL}/api"
