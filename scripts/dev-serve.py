#!/usr/bin/env python3
"""Tiny SPA dev server for nugudom.

Mirrors `firebase serve` in two ways:
  * Serves files out of the `public/` directory.
  * Falls back to `public/index.html` for any path that doesn't exist on
    disk, so `/bag`, `/cases`, etc. all reach the SPA router.

Run from the repo root:
    python3 scripts/dev-serve.py [port]
Default port is 5000.
"""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent.parent / "public"


class SPAHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        # Strip query / fragment to map to filesystem path.
        raw = self.path.split("?", 1)[0].split("#", 1)[0]
        target = (ROOT / raw.lstrip("/"))
        if raw == "/" or raw == "":
            return super().do_GET()
        if target.is_file():
            return super().do_GET()
        if target.is_dir() and (target / "index.html").is_file():
            return super().do_GET()
        # SPA fallback — serve index.html so the client-side router
        # picks up `/bag`, `/explore`, etc.
        self.path = "/index.html"
        return super().do_GET()

    def end_headers(self):
        # Match Firebase Hosting's no-cache directive for HTML so reloads
        # always pick up the latest build.
        if self.path.endswith(".html") or self.path == "/":
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    addr = ("", port)
    with ThreadingHTTPServer(addr, SPAHandler) as httpd:
        print(f"\n  ▸ nugudom dev server on http://localhost:{port}")
        print(f"    serving from {ROOT}")
        print("    SPA fallback enabled — /bag, /cases, /explore all resolve.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  ✦ bye")


if __name__ == "__main__":
    main()
