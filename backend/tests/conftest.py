"""Les tests d'intégration (marqueur `integration`) interrogent le backend déployé :
ils sont ignorés quand aucune URL n'est configurée (voir backend_url.py). Les
tests hors ligne (test_unit_models, test_api_offline) tournent partout."""
import pytest

from backend_url import BASE_URL


def pytest_collection_modifyitems(config, items):
    if BASE_URL:
        return
    skip = pytest.mark.skip(reason="backend déployé non configuré "
                                   "(REACT_APP_BACKEND_URL ou /app/frontend/.env)")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
