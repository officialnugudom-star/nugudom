#!/usr/bin/env python3
"""Tiny SPA dev server for nugudom.

Mirrors `firebase serve` in three ways:
  * Serves files out of the `public/` directory.
  * Falls back to `public/index.html` for any path that doesn't exist on
    disk, so `/bag`, `/cases`, etc. all reach the SPA router.
  * Honors HTTP Range requests so `<video>` can stream MP4s. Python's
    stock SimpleHTTPRequestHandler doesn't, which makes Chrome freeze
    the hero on the first frame.

Run from the repo root:
    python3 scripts/dev-serve.py [port]
Default port is 5000.
"""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent / "public"
CHUNK = 64 * 1024


class SPAHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    # ------- request dispatch -------
    def do_GET(self):
        raw = self.path.split("?", 1)[0].split("#", 1)[0]
        target = ROOT / raw.lstrip("/")
        is_real_file = target.is_file() or (
            target.is_dir() and (target / "index.html").is_file()
        )
        if not is_real_file and raw not in ("/", ""):
            # SPA fallback — index.html handles the route client-side.
            self.path = "/index.html"
            target = ROOT / "index.html"
            is_real_file = target.is_file()

        range_header = self.headers.get("Range") if is_real_file else None
        if range_header and target.is_file():
            try:
                return self._serve_range(target, range_header)
            except (BrokenPipeError, ConnectionResetError):
                return
        return super().do_GET()

    # ------- byte-range responder -------
    def _serve_range(self, fpath: Path, range_header: str):
        size = fpath.stat().st_size
        m = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if not m:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return
        start_s, end_s = m.group(1), m.group(2)
        if start_s == "" and end_s == "":
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return
        if start_s == "":
            # Suffix range: last N bytes
            length = min(int(end_s), size)
            start = size - length
            end = size - 1
        else:
            start = int(start_s)
            end = int(end_s) if end_s else size - 1
            if end >= size:
                end = size - 1
        if start < 0 or start >= size or start > end:
            self.send_response(416)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return
        length = end - start + 1
        ctype = self.guess_type(str(fpath))

        self.send_response(206)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(length))
        # end_headers() injects Accept-Ranges for us
        if str(fpath).endswith(".html"):
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()

        with open(fpath, "rb") as f:
            f.seek(start)
            sent = 0
            while sent < length:
                buf = f.read(min(CHUNK, length - sent))
                if not buf:
                    break
                try:
                    self.wfile.write(buf)
                except (BrokenPipeError, ConnectionResetError):
                    return
                sent += len(buf)

    # ------- always advertise range support + no-cache for HTML -------
    def end_headers(self):
        if not getattr(self, "_range_hdr_sent", False):
            self.send_header("Accept-Ranges", "bytes")
            self._range_hdr_sent = True
        if self.path.endswith(".html") or self.path == "/":
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    addr = ("", port)
    with ThreadingHTTPServer(addr, SPAHandler) as httpd:
        print(f"\n  ▸ nugudom dev server on http://localhost:{port}")
        print(f"    serving from {ROOT}")
        print("    SPA fallback enabled — /bag, /cases, /explore all resolve.")
        print("    HTTP Range supported — videos stream.\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n  ✦ bye")


if __name__ == "__main__":
    main()
