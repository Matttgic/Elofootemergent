"""URL du backend déployé, pour les tests d'intégration (marqueur `integration`).

Opt-in : définir REACT_APP_BACKEND_URL (ex. https://footpulse-api.onrender.com).
Sans elle, conftest.py ignore ces tests au lieu d'appeler une adresse codée en dur.
"""
import os

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE_URL}/api"
