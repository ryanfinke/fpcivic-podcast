# Podcast Listen Analytics — Setup

Private, cookieless listen tracking for the FPCA podcast. Two independent pieces:

1. **Website funnel** (Apps Script + Google Sheet) — plays + drop-off (10s / 25% /
   50% / 75% / 100%) from the website audio player. Emailed to you monthly.
2. **Podcast-app downloads** (OP3) — download counts across Apple/Spotify/etc.

Nothing is shown on the public site. All data stays in your **personal** Google
account (`ryan.finke@gmail.com`).

> Forward-only: analytics start counting once deployed. There is no way to
> recover past listens (GitHub Pages keeps no logs).

---

## Part 1 — Website funnel (do this on ryan.finke@gmail.com)

### A. Create the Apps Script
1. Sign in to <https://script.google.com> **as ryan.finke@gmail.com** (not the IFI account).
2. **New project** → rename it "FPCA Podcast Analytics".
3. Delete the placeholder code, paste the entire contents of `Analytics.gs`, **Save**.

### B. Run setup once
1. In the function dropdown pick **`setup`** → **Run**.
2. Authorize when prompted (Advanced → "Go to … (unsafe)" → Allow — normal for a
   personal script).
3. Check the **Execution log** — it prints the URL of a new private spreadsheet,
   "FPCA Podcast Analytics (private)", and confirms the monthly trigger installed.

### C. Deploy as a Web App
1. Click **Deploy → New deployment**.
2. Gear icon → select type **Web app**.
3. Set **Execute as: Me (ryan.finke@gmail.com)** and **Who has access: Anyone**.
   - "Anyone" is required so the website can post events. It's safe — the endpoint
     only *appends* anonymous event rows; it never returns any data.
4. **Deploy**, authorize if asked, and **copy the Web app URL**
   (looks like `https://script.google.com/macros/s/AKfyc…/exec`).

### D. Wire it into the site
- Send me that Web app URL (or paste it yourself into `index.html`):
  ```js
  const ANALYTICS_ENDPOINT = "https://script.google.com/macros/s/AKfyc…/exec";
  ```
- Redeploy the site. Until this URL is set, the player simply records nothing.

### Test / use
- Play an episode on the live site for ~10+ seconds; a row should appear in the
  spreadsheet within a few seconds.
- The monthly funnel email arrives on the **1st of each month**. To preview now,
  run **`emailReportNow`** from the editor.

---

## Part 2 — Podcast-app download counts (OP3)

Already wired in code: the RSS feed's episode URLs are prefixed with
`https://op3.dev/e/…`, so every podcast-app download is counted by
[OP3](https://op3.dev) (free, open-source, privacy-friendly).

- View counts at <https://op3.dev> — look up the show by its feed URL
  (`https://ryanfinke.github.io/fpcivic-podcast/feed.xml`).
- OP3 gives **download counts per episode**, not drop-off — podcast apps never
  report playback progress, so quartile drop-off is website-only.
- To turn OP3 off, set `USE_OP3 = False` in `scripts/generate.py`.
