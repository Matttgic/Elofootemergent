"""Normalisation des noms d'équipe, commune à tous les rapprochements entre
sources (football-data, Understat, FotMob, The Odds API)."""
import re
import unicodedata

# Mots sans valeur distinctive : formes juridiques, « club », articles, sigles
# de sections sportives et années de fondation.
STOP_WORDS = {
    "fc", "cf", "ac", "as", "sc", "ss", "rc", "cd", "sd", "ud", "sv", "bc", "bk", "sk", "if", "us",
    "afc", "sad", "vfl", "vfb", "tsg", "hsv", "club", "de", "the", "calcio", "balompie",
    "1", "04", "05", "09", "1846", "1899", "1900", "1904", "1907", "1913",
}
# Lettres sans décomposition Unicode (sinon perdues par la conversion ASCII)
_TRANSLIT = str.maketrans({"ø": "o", "æ": "ae", "ß": "ss", "ł": "l", "đ": "d", "ı": "i"})


def normalize_team_name(name):
    """« 1. FC Köln » -> « koln », « Real Betis Balompié » -> « real betis »."""
    s = str(name or "").lower().translate(_TRANSLIT)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return " ".join(t for t in re.sub(r"[^a-z0-9]", " ", s).split() if t not in STOP_WORDS)
