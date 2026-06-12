# NUGUDOM handoff for next Claude session

Copy this whole document, or attach it as the first message to the next Claude session.

---

## 1. PROJECT OVERVIEW

NUGUDOM is a non-commercial fan site for underrated K-pop artists ("nugus"). Users can discover nugus, design photocards in a studio (CSS-composited bg + stickers + laminate + shape), and publish them to EXPLORE.

Owner went non-commercial on 2026-05-27. Skip any sales/commercial features. Commercial API rate limits (Apple Music, Reddit, X) don't apply since the site is non-commercial.

- Live URL: https://nugudom.org (also https://nuguu-1956e.web.app)
- Tech: static SPA in a single ~28k-line `public/index.html`, deployed to Firebase Hosting. Firebase Firestore for data, Firebase Storage for user uploads. GitHub Actions auto-deploys on push to main. Cloudflare Worker proxies Apify for Spotify scraping.

---

## 2. WHERE THE CODE LIVES

- GitHub repo: `github.com/officialnugudom-star/nugudom` (main branch)
- Clone command: `git clone https://github.com/officialnugudom-star/nugudom.git`
- Suggested local path: `~/nugudom`
- Latest commit before this handoff: `5ea56a9` ("Hero slides: add SUMMER CAKE / Not In Public as slide 9")

---

## 3. ACCOUNTS + LOGINS

| Service | Account | Where to login | Notes |
|---|---|---|---|
| GitHub | `officialnugudom-star` | github.com | Needs a Personal Access Token with `repo` + `workflow` scopes for git push. Make one at github.com/settings/tokens. |
| Firebase / Google Cloud | `leizz3000@gmail.com` (admin) plus `officialnugudom@gmail.com` (project owner) | console.firebase.google.com → project `nuguu-1956e` | After reset: install firebase CLI (`npm install -g firebase-tools`) then `firebase login`. |
| Cloudflare | `officialnugudom@gmail.com` | dash.cloudflare.com | Has one Worker called `nugudom-spotify-proxy` with an encrypted secret `APIFY_TOKEN`. Both survive reset. |
| Apify | email login at apify.com | apify.com → Settings → Integrations → Personal API tokens | The token is already saved in the Cloudflare Worker secret. You only need to login if you want to view usage / change plan. Free tier: $5/mo credits. |
| YouTube Data API v3 | inside the `NUGUU` project on Google Cloud | console.cloud.google.com → APIs & Services → Credentials | The API key is restricted to nugudom.org + nuguu-1956e.web.app + localhost:5000. ROTATE THIS KEY AFTER RESET because it was pasted in conversation logs. Delete the existing one, make a new one with the same restrictions, paste it into nugudom when ⤓ FETCH ALL YT SUBS prompts. |
| Spotify Developer | not set up. Don't need it. | Use Apify's pathfinder scraper instead. | Spotify requires Premium on the dev account since Feb 2026 and never exposed monthly listeners anyway. |

Admin email for site privileges: `leizz3000@gmail.com`. The site's `isAdmin()` returns true only for that email plus two `*@nuguudom.com` addresses.

---

## 4. INFRA LAYOUT

```
nugudom.org
  ├─ Firebase Hosting (project nuguu-1956e)
  │    └─ serves public/index.html + assets + 9 video files
  ├─ Firebase Firestore
  │    └─ users/, artists/, publicCases/, meta/heroCards, etc.
  ├─ Firebase Storage
  │    └─ user_case_photos/, user_bgs/, user_stickers/
  └─ Cloudflare Worker (nugudom-spotify-proxy.officialnugudom.workers.dev)
       └─ /batch endpoint → Apify Spotify actor → returns listeners + followers

GitHub Actions (.github/workflows/firebase-deploy.yml)
  └─ on every push to main, runs FirebaseExtended/action-hosting-deploy
       Secret used: FIREBASE_SERVICE_ACCOUNT (already configured in repo)
```

---

## 5. ADMIN TOOLS ON THE LIVE SITE

Sign in as `leizz3000@gmail.com`. Click ⚙ ADMIN in the top right of the page. The drawer has:

- + ADD NUGU
- ALL USERS ✦
- DATASET ✦ (bulk Spotify + YouTube editor with per-row FETCH buttons)
- SALES PREP ✦ (unused since site went non-commercial)
- 📦 EXPORT CASES ✦
- ↺ BACKFILL UPLOADS ✦
- ↻ RECOVER FROM OWNERS' CASES ✦
- 🧹 CLEAR ALL BAKES ✦ (should be a no-op now)
- ⤓ FETCH ALL YT SUBS ✦ (uses localStorage API key, prompts if not set)
- ⤓ FETCH ALL SPOTIFY ✦ (uses Apify via CF Worker, no prompt)
- HERO PICKS ✦
- FEATURED ✦
- UPDATES ✦

---

## 6. WHAT IS DONE / WORKING

- Hero with 9 videos (Itzel, Dragon Pony, Tomatomat, hrtz.wav, MEMI, HITGS, Re:Hearts, GHOST9, SUMMER CAKE), each 30s trimmed
- Pause/play + sound toggle on hero
- Sign-in works (3 dead entry points were fixed in commit 6d544b9)
- Studio photo picker rebuilds on open + has inline upload + handles individually-collected band members
- Spotify auto-fetch via Cloudflare Worker → Apify
- YouTube subscriber fetch via Google API
- Dataset panel: per-row Spotify + YouTube fetch buttons
- Photocard tap in collected section opens the nugu modal (not editor)
- Portrait phones get a dismissible "rotate for full layout" banner
- Nugus page fits everything on a single page when total ≤ ~60

---

## 7. WHAT IS REMOVED / DO NOT REINTRODUCE

Client-side photocard baking is removed (commit 3bdbb8b). Do NOT bring it back.

The bake step rendered photocards to a single 660×1020 canvas → PNG → uploaded to Storage as `flatFront`. EXPLORE then served the card as one `<img>` instead of compositing layers live. The problem: `canvas.getImageData()` requires CORS access to read pixel data. Most wallpaper + sticker hosts don't return CORS headers. Canvas would silently fail to load those images, bake a photo-on-white PNG, and EXPLORE would show the wrong card.

Two prior Claude sessions burned hours on this. The root cause is unfixable in the browser. The site now always renders structured (bg + photo + stickers as separate DOM nodes). Slower per tile but always correct, zero Storage cost.

If a future session is asked "speed up EXPLORE with flat images" or "make the bake work": the only viable paths are server-side bake via Cloud Function with node-canvas (needs Blaze plan + functions/ directory) OR fixing CORS at the asset source. Both are real work and require user approval first.

---

## 8. KNOWN GOTCHAS

- YouTube API key lives in localStorage (`nugudom_yt_api_key`). Anything that clears site data wipes it.
- GitHub push needs the `workflow` scope on the token if you ever change .github/workflows/ files.
- Firebase Hosting deploys are atomic full-replacement. Videos must be in the repo (they are now) so pushes don't wipe them off the live CDN.
- Cloudflare Worker IPs and GitHub Actions IPs are both blocked by Spotify. That's why we route Spotify through Apify (residential proxies).
- YouTube subscriber counts are rounded by YouTube's API (66,432 → 66,400). Not a bug, that's their public policy since 2019.
- Spotify is the more accurate stat for nugu ranking.
- The bake button is gone but CLEAR ALL BAKES + RECOVER FROM OWNERS' CASES stay as safety nets. They should be no-ops now.

---

## 9. THINGS IN FLIGHT

- Logo concepts page at `nugudom.org/logo.html` has 6 design options. User was supposed to pick one to wire into the topbar + favicon. Nothing committed beyond the preview page itself.
- Move videos to Firebase Storage / a CDN. Mentioned but not done. Currently videos are committed to the repo (~50 MB). Long-term plan was Cloudflare R2 or Storage for cheaper egress.
- Compress user photo uploads client-side. Mentioned but not done. Would help Storage costs.
- Regression model on nugu growth. Discussed but recommended to wait until late summer 2026 when there's enough time-series data.

---

## 10. MEMORY FILES TO RECREATE

Write these into `~/.claude/projects/-Users-<your-username>/memory/` after the reset, or paste them as context to the next Claude session.

### `nugudom-repo.md`

NUGUDOM's source is at github.com/officialnugudom-star/nugudom (org: officialnugudom-star, repo: nugudom). Main branch is main. Deploys to Firebase Hosting via the firebase-deploy.yml workflow on push to main.
Suggested local clone path: ~/nugudom.

### `nugudom-noncommercial.md`

As of 2026-05-27 the owner decided NUGUDOM will NOT sell anything. Don't build, surface, or push commercial/sales features. Treat the site as a non-commercial fan project. Third-party API commercial-use restrictions (Apple Music/iTunes Search, Reddit Data API, X API) do NOT apply.

### `nugudom-photocard-rendering.md`

Canonical photocard markup:

```
.fav-tile.case-tile[.skinClass][.has-bg]
  > .ph[data-no=...]
      > <img src="photoUrl" referrerpolicy="no-referrer">
      > .sticker-layer.view-only > .stk[positioned %]
  > [pcWatermark]
```

Proportions (do NOT guess):
- .fav-tile padding: 13% 13% 18% (sides 13, top 13, bottom 18 = thumb-notch / watermark zone)
- .fav-tile .ph aspect-ratio: 55/85
- .fav-tile .ph img: width 100% height 100% object-fit cover
- Natural outer ratio of a .fav-tile = width/height ~ 0.688

Composition logic:
- A "case template" lives in window._myCases keyed by case id.
- A "photo" is any image URL.
- A "photocard" = applying a case template to a photo.
- flatFront (if present) is a pre-rendered PNG of the whole card.

Don't synthesize fake "case styles" (clear/holo/sparkle/bow as fake variants) - cases ARE user-designed templates.
Don't force a hard outer aspect-ratio (11/17, 4/5) - let .fav-tile size itself via padding + 55/85 inner photo.
Don't reinvent the markup - use the canonical pattern.
.pc-wm font-sizes are FIXED px and don't scale - override per-context for large tiles.

### `nugudom-publish-bake.md`

NUGUDOM no longer bakes photocards client-side. `_doPublishNugu` always writes the structured design (bg + previewPhoto + stickers + shape + laminate + flipH + back). EXPLORE / featured / detail / profile renderers composite live in the DOM.

Bake was removed in commit 3bdbb8b. Reason: client-side baking requires canvas.getImageData() on cross-origin images, which the browser refuses without Access-Control-Allow-Origin headers. Most NUGUDOM asset hosts don't send those headers. Every variation tried (aggressive validator, looser validator, strict abort) either shipped corrupt PNGs or refused to bake. Going non-commercial made the perf and storage wins moot.

Two prior Claude sessions burned hours here. Do NOT reintroduce client-side bake. The only paths that actually work:
1. Server-side bake via Cloud Function (Blaze plan + functions/ directory + node-canvas)
2. Image-proxy Cloud Function (Blaze plan)
3. Fix CORS at the asset source (only feasible for Firebase-hosted assets, not Pinterest etc)

If a user reports "case disappeared after publishing", it's almost certainly stale flatFront on an old publicCases doc. CLEAR ALL BAKES admin button handles it. RECOVER FROM OWNERS' CASES handles the destructively-baked old ones.

### `no-emdash-natural-language.md`

Owner does not want em dashes. Write conversational, not AI-style bullet recaps. Use natural language. Personal preference.

---

## 11. KICKOFF MESSAGE FOR THE NEXT CLAUDE

Use this as your first prompt to the next Claude after the reset:

> I just reset my computer. NUGUDOM lives at github.com/officialnugudom-star/nugudom. Clone it to ~/nugudom and set up firebase CLI (`firebase login`) using leizz3000@gmail.com. I'm pasting the handoff doc below — please ingest it, save the four memory files to your memory directory, and confirm everything is set up before we start new work.
>
> [paste this entire handoff document]

Then attach this whole document.
