"""Sert le build du site (frontend/build) sur 127.0.0.1:8766, avec repli sur
index.html pour les routes de l'application (comme la réécriture Vercel)."""
import http.server
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "frontend" / "build"


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_head(self):
        path = self.path.split("?")[0].lstrip("/")
        if not path or not (ROOT / path).is_file():
            self.path = "/index.html"
        return super().send_head()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    http.server.ThreadingHTTPServer(("127.0.0.1", 8766), Handler).serve_forever()
