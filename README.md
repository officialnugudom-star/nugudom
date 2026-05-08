# NUGUDOM 🎵

**Discover Unknown K-Pop** — a community site for supporting underrated K-pop artists (nugus).

Built as a single-page app on Firebase Hosting + Firestore.

## Live Site
[nugudom.org](https://nugudom.org)

## Stack
- **Frontend:** Vanilla HTML/CSS/JS (single `index.html`)
- **Backend:** Firebase Firestore (database), Firebase Auth, Firebase Storage
- **Hosting:** Firebase Hosting
- **APIs:** YouTube Data API v3, Wikipedia API

## Features
- Browse & vote on nugu artists
- Spotify listener & YouTube subscriber tracking
- Community discussions & comments
- Nugu request system
- User profiles with favorites & discoveries
- Admin tools (add nugus, daily stats logger, dataset viewer)
- Pink / Blue / Black / White themes

## Project Structure
```
nugudom/
├── public/
│   └── index.html      # Entire app (HTML + CSS + JS)
├── firebase.json       # Firebase Hosting config
├── .firebaserc         # Firebase project reference
└── .gitignore
```

## Deploy

```bash
# Install Firebase CLI (once)
npm install -g firebase-tools

# Login
firebase login

# Deploy
firebase deploy
```

## Firebase Project
- **Project ID:** `nuguu-1956e`
- **Auth Domain:** `nuguu-1956e.firebaseapp.com`
- **Storage Bucket:** `nuguu-1956e.firebasestorage.app`

## Contact
- Email: officialnugudom@gmail.com
- TikTok: [@nuguuofficial](https://www.tiktok.com/@nuguuofficial)

---
*made with ♡ for unsung k-pop. spread the love, stream the b-sides, vote the underdogs.*
