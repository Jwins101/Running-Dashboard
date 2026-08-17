# Running dashboard — hosting setup

This folder is a small static site: `running_dashboard.html` fetches
`data.json` for its running history, and a scheduled script
(`sync_garmin.py`) regenerates `data.json` from Garmin once a day.

## 1. Host it with GitHub Pages (free, ~10 minutes)

1. Create a new **private or public** GitHub repo (private is fine — Pages
   works either way on a free plan as long as the repo owner has Pages
   enabled; if your account doesn't support private-repo Pages, make it
   public — nothing in `data.json` is sensitive beyond your own run data).
2. Push everything in this folder to that repo, keeping the folder
   structure (the `.github/workflows/sync.yml` path matters).
3. In the repo, go to **Settings → Secrets and variables → Actions** and
   add two repository secrets:
   - `GARMIN_EMAIL`
   - `GARMIN_PASSWORD`
4. In **Settings → Pages**, set the source to "Deploy from a branch",
   branch `main`, folder `/ (root)`.
5. Rename `running_dashboard.html` to `index.html` (or set Pages to serve
   the specific file) so it loads at your Pages URL directly, e.g.
   `https://yourname.github.io/running-dashboard/`.

That's it — GitHub now serves the page for free, and the Action pulls
fresh Garmin data daily and commits it, which auto-redeploys the page.

## 2. How the daily refresh actually works

I can't run background jobs myself — I only act when you message me in a
chat. So instead of me refreshing it, `sync_garmin.py` does the pulling,
and GitHub Actions' cron scheduler (`.github/workflows/sync.yml`) is what
runs it daily at 11:00 UTC. It logs into Garmin using the two secrets
above, rewrites `data.json`, and commits it — the live page picks it up
on next load since it fetches `data.json` fresh each time (no cache).

You can trigger it manually anytime from the repo's **Actions** tab via
"Run workflow" instead of waiting for the schedule.

## 3. Other hosting options

GitHub Pages + Actions is the simplest free combo since scheduling and
hosting live in the same place. Alternatives if you'd rather not use
GitHub:
- **Netlify** or **Vercel**: host the static files the same way, but
  you'd need a separate scheduler for the sync script (e.g. a free tier
  of [cron-job.org](https://cron-job.org) hitting a small serverless
  function, or GitHub Actions alone just for the sync step while Netlify/
  Vercel serves the files from the same repo).
- **A personal server / Raspberry Pi**: run `sync_garmin.py` via a plain
  cron entry (`0 7 * * * cd /path/to/dashboard && python3 sync_garmin.py`)
  and serve the folder with any static file server (`python3 -m http.server`
  behind a reverse proxy, nginx, Caddy, etc.).

## 4. Local use without hosting

If you just want to keep opening the HTML file directly (no hosting), it
still works — it'll silently fall back to the snapshot of your history
that's baked into the file, and the "Log a run" section will keep
working via browser-side storage either way.

## 5. Security note

`GARMIN_PASSWORD` as a GitHub secret is reasonably safe (secrets are
encrypted and never printed in logs), but it's still your real account
password living in a third-party system. If you'd rather not do that,
Garmin also supports app-specific tokens in some client libraries — worth
checking `garminconnect`'s docs if that matters to you.
