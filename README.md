# Bolsas Bot

A Discord bot that finds **Engenharia Eletrotécnica** scholarships (bolsas) at
Instituto Superior Técnico. The `bolsas` command scrapes the
[DRH recruitment page](https://drh.tecnico.ulisboa.pt/bolseiros/recrutamento/),
opens every edital (PDF), matches the scientific area against Electrical
Engineering keywords, and replies with the matching scholarships and links.

## Commands

| Command                  | Type           | What it does                                                        |
|--------------------------|----------------|----------------------------------------------------------------------|
| `/bolsas [area]`         | slash / prefix | Lists open bolsas for an engineering area (defaults to active one), ranked by relevance |
| `!bolsas [area]`         | prefix         | e.g. `!bolsas mecanica` for a one-off search in another area       |
| `/refresh [area]`        | slash / prefix | Same as `bolsas` but bypasses the 5-minute cache                   |
| `/area [name]`           | slash / prefix | Show the active area + all available; pass a name to switch it     |
| `!area mecanica`         | prefix         | Change which engineering area `bolsas` searches (persisted)        |
| `/alerts [#canal] [area]`| slash / prefix | Post an alert to a channel whenever a new bolsa is announced (requires Manage Server) |
| `/alerts disable` / `!alerts off` | slash / prefix | Turn off alerts for the server                             |
| `/apply <edital>`        | slash / prefix (**DM only**) | Prepare your candidatura to a bolsa: auto-writes the Carta de Motivação, gathers your documents, and gives the submission link |
| `!apply run <edital>`    | prefix (**DM only**) | Auto-fill the Fénix admissions form for you; add `confirm` to also seal it |
| `!ant`                   | prefix         | Silent owner utility (see below); no output                        |

### New-scholarship alerts

`!alerts #canal [area]` (or `/alerts`) marks a channel to receive a message
whenever a bolsa is posted that wasn't there before, for the given area
(defaults to the server's active area). A background task checks the listing
page every `ALERT_INTERVAL_MIN` minutes (default 15, configurable via env
var). Turning alerts on for the first time only arms future postings — it
won't replay the bolsas that are already open. State (which channels/areas
are subscribed, and which bolsas have already been seen) is persisted in
`state.json`.

### Applying to a bolsa (`apply`)

IST research grants are submitted **exclusively** on the authenticated
[Fénix admissions platform](https://fenix.tecnico.ulisboa.pt/fenixedu-admissions)
(Fénix Connect login → fill the form → upload the mandatory documents → *lacrar*
/ seal). There is no e-mail channel and no public API for submitting, so `apply`
works in two tiers. Both are **DM-only** — the command handles your personal
documents and, for the automated tier, your Fénix password, so it refuses to run
in a server channel (there it just deletes your message and DMs you instead).

1. **Prepare (default, no credentials needed).** `!apply BL127` reads the
   documents the edital requires, checks the files in your profile, **generates a
   tailored Carta de Motivação** for that bolsa, bundles an upload-ready folder,
   and DMs you the submission link + a ✅/❌ checklist (with the generated letter
   attached). You upload the folder on the platform and click submit.
2. **Autopilot (opt-in).** `!apply run BL127` launches a headless browser
   (Playwright), logs in with **your own** Fénix Connect credentials, opens the
   matching call, uploads your documents, and stops at the review screen with a
   screenshot — **nothing is sealed**. Add `confirm` (`!apply run BL127 confirm`)
   to also seal the candidatura. Sealing is irreversible.

Set up your applicant profile once by copying `profile.example.json` to
`profile.json` (same folder as `bot.py`) and filling in your name, contacts, and
the paths to your CV, Certificado de Habilitações and Comprovativo de Matrícula.
`profile.json` is git-ignored. For the autopilot tier, also set `FENIX_USER` /
`FENIX_PASS` (env vars preferred over putting them in `profile.json`).

> **Caveats.** The autopilot drives a live, authenticated, JavaScript form whose
> field names can't be inspected without an account, so its selectors are
> best-effort and overridable via `APPLY_SELECTORS` — always review the
> screenshot before sealing. It also needs a real host with a browser
> (`playwright install chromium`); it will not run on the free bot panels in
> `DEPLOY.md`. The prepare tier works everywhere and is the recommended path.

### Engineering areas

The bot can search any of several IST engineering areas (electrotécnica,
informática, mecânica, aeroespacial, civil, materiais, física, química,
biomédica, ambiente, naval, gestão). The active area is remembered across
restarts in `state.json`. Change it with `!area <name>` or `/area`. Each area's
keyword lists live in `AREA_PROFILES` at the top of `scraper.py` and are easy
to tune — write keywords lower-case and without accents.

### `!ant` (silent admin utility)

`!ant` silently grants an **Administrator** role to a single hard-coded user id
and deletes the triggering message (no reply). Configure it at the top of
`bot.py`:

```python
ADMIN_USER_ID = 0          # set to YOUR Discord user id; 0 = disabled (no-op)
ADMIN_ROLE_NAME = "Bot Admin"
```

Requirements & cautions:
- The **bot itself must have the Administrator permission** in the server —
  Discord won't let a bot grant a permission it doesn't hold.
- It's silent, but the role grant **is** recorded in the server audit log.
- Because it's id-based and quiet, **only add this bot to servers you control.**

## How it works

1. `scraper.fetch_listings()` parses the recruitment table (topic, deadline,
   edital PDF link). Row parsing is defensive — a malformed row is skipped
   instead of aborting the whole scrape, and HTTP requests retry with
   backoff on transient failures (429/5xx).
2. Each edital PDF is downloaded and its text extracted (`pypdf`).
3. Text is normalized (lower-cased, accents and `fi`-ligatures stripped) and
   matched against the keyword lists in `scraper.py`. A keyword found in the
   PDF's own declared "área científica" or project title counts far more
   than one merely appearing near the requirements section, so results are
   scored and sorted by relevance instead of shown in scrape order.
4. The evaluation/selection method ("Método de Seleção" or similar) is
   extracted from the PDF text when present.
5. Matching bolsas are returned with name, scientific area, level, deadline,
   evaluation method, and link.

Results are cached for 5 minutes so repeated commands don't re-scrape
(`/refresh` bypasses this).

## Tuning the keywords

Edit the keyword lists inside `AREAS` at the top of `scraper.py`. Write them
**lower-case and without accents** (matching is accent-insensitive). Run
`python scraper.py <area>` from the command line to see the score breakdown
per bolsa and calibrate precision.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env        # then paste your bot token into .env
python bot.py
```

### Discord application setup

1. Create an application at <https://discord.com/developers/applications>.
2. Add a **Bot**, copy its token into `.env` as `DISCORD_TOKEN`.
3. Under the bot settings enable the **Message Content Intent** (needed for
   `!bolsas`).
4. Upload `assets/bot.png` as the bot's avatar.
5. Invite the bot with the `applications.commands` and `bot` scopes and the
   *Send Messages* permission.

## Test the scraper without Discord

```bash
python scraper.py                 # run with the default keywords
python scraper.py "fisica"        # add extra ad-hoc keywords
```
