#!/usr/bin/env python3
"""Weekly Spotify stats sync for NUGUDOM.

Walks every artist with a spotifyUrl, pulls monthlyListeners + followers
via Spotify's unofficial pathfinder GraphQL endpoint, and writes them
back to Firestore (artists/<id> + a YYYY-MM-DD snapshot under each of
listenerHistory / followerHistory).

Why the unofficial endpoint instead of the Spotify Web API:
- Official `/v1/artists/{id}` requires a Spotify Developer app, which
  since Feb 2026 requires Spotify Premium on the developer side.
- Monthly listeners has never been exposed by any official API.
- pathfinder returns both stats from one call with just an anonymous
  bearer token (no Spotify account required).

If the pathfinder primary path fails (most often: stale persistedQuery
hash after a Spotify web build push), the script falls back to scraping
the artist page's `<meta name="description">` tag, which always contains
the monthly-listener count in plain text. Followers can't be recovered
from the meta tag, so those will be missing on fallback weeks until
the hash gets refreshed.

Run via GitHub Actions weekly. Credentials come from env vars:
- FIREBASE_SERVICE_ACCOUNT: the entire service account JSON, as a single
  env var. Reuses the same secret the firebase-deploy workflow uses.
- SPOTIFY_QUERY_HASH (optional): manual override for the persistedQuery
  hash if auto-discovery breaks.
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone

import requests
import firebase_admin
from firebase_admin import credentials, firestore

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
SPOTIFY_ID_RE = re.compile(r"open\.spotify\.com/artist/([A-Za-z0-9]+)")
TOKEN_URL = (
    "https://open.spotify.com/get_access_token"
    "?reason=transport&productType=web-player"
)
PATHFINDER_URL = "https://api-partner.spotify.com/pathfinder/v1/query"
HOME_URL = "https://open.spotify.com/"


def get_anon_token():
    r = requests.get(
        TOKEN_URL,
        headers={"User-Agent": UA, "App-Platform": "WebPlayer"},
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["accessToken"]


def discover_query_hash():
    """Scrape the current queryArtistOverview hash from the web-player bundle.

    Spotify rotates persistedQuery hashes every few web-player releases.
    The hash lives in one of several Webpack chunks referenced from
    open.spotify.com's HTML. Permissive search: pull every .js URL the
    page references, fetch each in order, look for the hash near the
    operation name. Returns None if nothing in the chain matches.
    """
    try:
        r = requests.get(
            HOME_URL,
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=20,
        )
        r.raise_for_status()
        html = r.text
        bundles = re.findall(r'https?://[^"\s>]+?\.js(?:\?[^"\s>]*)?', html)
        seen = set()
        bundles = [b for b in bundles if not (b in seen or seen.add(b))]
        print(f"  searching {len(bundles)} JS bundles for the hash…")
        if not bundles:
            print(f"  WARN: no .js bundles found in HTML (len={len(html)}); first 300 chars:")
            print(f"  {html[:300]!r}")
            return None
        for i, url in enumerate(bundles):
            try:
                br = requests.get(url, headers={"User-Agent": UA}, timeout=30)
                if br.status_code != 200:
                    continue
                js = br.text
                m = re.search(
                    r'queryArtistOverview"[^"]{0,200}"sha256Hash":"([a-f0-9]{64})"',
                    js,
                )
                if not m:
                    m = re.search(
                        r'"sha256Hash":"([a-f0-9]{64})"[^"]{0,200}queryArtistOverview',
                        js,
                    )
                if m:
                    bundle_name = url.split("/")[-1].split("?")[0]
                    print(f"  hash found in bundle {i+1}/{len(bundles)}: {bundle_name}")
                    return m.group(1)
            except Exception:
                continue
        print(f"  WARN: scanned all {len(bundles)} bundles, no match")
    except Exception as e:
        print(f"  discovery error: {e}")
        return None
    return None


def fetch_pathfinder(token, artist_id, query_hash):
    variables = {"uri": f"spotify:artist:{artist_id}", "locale": ""}
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": query_hash}}
    params = {
        "operationName": "queryArtistOverview",
        "variables": json.dumps(variables, separators=(",", ":")),
        "extensions": json.dumps(extensions, separators=(",", ":")),
    }
    r = requests.get(
        PATHFINDER_URL,
        params=params,
        headers={
            "Authorization": f"Bearer {token}",
            "App-Platform": "WebPlayer",
            "User-Agent": UA,
            "Accept": "application/json",
        },
        timeout=20,
    )
    if r.status_code != 200:
        raise RuntimeError(f"http {r.status_code}: {r.text[:200]}")
    data = r.json()
    if "errors" in data:
        raise RuntimeError(f"graphql error: {data['errors'][:1]}")
    artist = (data.get("data") or {}).get("artistUnion") or {}
    stats = artist.get("stats") or {}
    return {
        "monthlyListeners": stats.get("monthlyListeners"),
        "followers": stats.get("followers"),
    }


NUM_SUFFIX = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}
LISTENERS_RE = re.compile(
    r"(\d[\d,\.]*)\s*([KMB])?\s*monthly listener",
    re.IGNORECASE,
)


def parse_count(s, suffix=None):
    s = (s or "").strip().replace(",", "")
    try:
        n = float(s)
    except ValueError:
        return None
    if suffix:
        n *= NUM_SUFFIX.get(suffix.upper(), 1)
    return int(n)


def fetch_html_meta(artist_id, debug=False):
    """Fallback: scrape monthly listeners from the artist page metadata.

    Spotify embeds 'X monthly listeners' in the page's OpenGraph / Twitter
    / standard description for SEO. The page renders even when API access
    is blocked, so this survives pathfinder breakage. Doesn't carry
    followers - those wait for the pathfinder path to come back.
    """
    url = f"https://open.spotify.com/artist/{artist_id}"
    r = requests.get(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        timeout=20,
    )
    if r.status_code != 200:
        if debug:
            print(f"    meta fetch http {r.status_code}")
        return {"monthlyListeners": None, "followers": None}
    html = r.text
    candidates = []
    for pattern in [
        r'<meta\s+property="og:description"\s+content="([^"]+)"',
        r'<meta\s+name="twitter:description"\s+content="([^"]+)"',
        r'<meta\s+name="description"\s+content="([^"]+)"',
        r'<meta\s+property="description"\s+content="([^"]+)"',
    ]:
        for m in re.finditer(pattern, html, re.IGNORECASE):
            candidates.append(m.group(1))
    if not candidates:
        if debug:
            print(f"    no meta description tags in page (len={len(html)}); first 200:")
            print(f"    {html[:200]!r}")
        return {"monthlyListeners": None, "followers": None}
    for desc in candidates:
        m = LISTENERS_RE.search(desc)
        if m:
            n = parse_count(m.group(1), m.group(2))
            if n is not None:
                return {"monthlyListeners": n, "followers": None}
    if debug:
        print(f"    meta tags present but no 'monthly listeners' match. First desc: {candidates[0][:160]!r}")
    return {"monthlyListeners": None, "followers": None}


def init_firestore():
    raw = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
    if not raw:
        print("FIREBASE_SERVICE_ACCOUNT env var not set", file=sys.stderr)
        sys.exit(1)
    cred = credentials.Certificate(json.loads(raw))
    firebase_admin.initialize_app(cred)
    return firestore.client()


def main():
    db = init_firestore()
    query_hash = os.environ.get("SPOTIFY_QUERY_HASH") or discover_query_hash()
    if query_hash:
        print(f"using persistedQuery hash: {query_hash[:12]}…")
    else:
        print("no persistedQuery hash available - HTML fallback only")

    token = None
    if query_hash:
        try:
            token = get_anon_token()
        except Exception as e:
            print(f"anon token fetch failed: {e}", file=sys.stderr)
            query_hash = None  # force fallback

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    print(f"snapshot date: {today}")

    ok = skip = fail = 0
    failures = []
    for doc in db.collection("artists").stream():
        a = doc.to_dict() or {}
        name = a.get("name") or "(unnamed)"
        url = a.get("spotifyUrl") or ""
        m = SPOTIFY_ID_RE.search(url)
        if not m:
            skip += 1
            continue
        artist_id = m.group(1)

        stats = {"monthlyListeners": None, "followers": None}
        used = "pathfinder"
        debug_this = (ok + fail) < 3  # verbose for the first 3 attempts only
        if token and query_hash:
            try:
                stats = fetch_pathfinder(token, artist_id, query_hash)
            except Exception as e:
                print(f"  ! {name}: pathfinder failed ({e}); falling back", file=sys.stderr)
                used = "meta-fallback"
                try:
                    stats = fetch_html_meta(artist_id, debug=debug_this)
                except Exception as e2:
                    fail += 1
                    failures.append(f"{name}: pathfinder + fallback failed ({e2})")
                    continue
        else:
            used = "meta-fallback"
            try:
                stats = fetch_html_meta(artist_id, debug=debug_this)
            except Exception as e:
                fail += 1
                failures.append(f"{name}: meta fetch failed ({e})")
                continue

        listeners = stats.get("monthlyListeners")
        followers = stats.get("followers")
        if listeners is None and followers is None:
            fail += 1
            failures.append(f"{name}: no stats in response ({used})")
            continue

        updates = {"fetchedAt": firestore.SERVER_TIMESTAMP}
        if listeners is not None:
            updates["spotifyMonthlyListeners"] = int(listeners)
        if followers is not None:
            updates["spotifyFollowers"] = int(followers)
        try:
            ref = db.collection("artists").document(doc.id)
            ref.update(updates)
            if listeners is not None:
                ref.collection("listenerHistory").document(today).set(
                    {"listeners": int(listeners), "recordedAt": firestore.SERVER_TIMESTAMP}
                )
            if followers is not None:
                ref.collection("followerHistory").document(today).set(
                    {"followers": int(followers), "recordedAt": firestore.SERVER_TIMESTAMP}
                )
            ok += 1
            print(
                f"  ✓ {name}: "
                f"listeners={listeners if listeners is not None else '—'} · "
                f"followers={followers if followers is not None else '—'} "
                f"[{used}]"
            )
        except Exception as e:
            fail += 1
            failures.append(f"{name}: firestore write failed ({e})")

        time.sleep(0.5)

    print(f"\ndone · ok={ok} skip={skip} fail={fail}")
    if failures:
        print("\nfailures:")
        for f in failures[:15]:
            print(f"  - {f}")
    if fail and not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
