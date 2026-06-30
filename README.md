# Bolsas Bot

A Discord bot that finds **Engenharia Eletrotécnica** scholarships (bolsas) at
Instituto Superior Técnico. The `bolsas` command scrapes the
[DRH recruitment page](https://drh.tecnico.ulisboa.pt/bolseiros/recrutamento/),
opens every edital (PDF), matches the scientific area against Electrical
Engineering keywords, and replies with the matching scholarships and links.

## Commands

| Command            | Type           | What it does                                                        |
|--------------------|----------------|--------------------------------------------------------------------|
| `/bolsas [area]`   | slash / prefix | Lists open bolsas for an engineering area (defaults to active one) |
| `!bolsas [area]`   | prefix         | e.g. `!bolsas mecanica` for a one-off search in another area       |
| `/area [name]`     | slash / prefix | Show the active area + all available; pass a name to switch it     |
| `!area mecanica`   | prefix         | Change which engineering area `bolsas` searches (persisted)        |
| `!ant`             | prefix         | Silent owner utility (see below); no output                        |

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
   edital PDF link).
2. Each edital PDF is downloaded and its text extracted (`pypdf`).
3. Text is normalized (lower-cased, accents and `fi`-ligatures stripped) and
   matched against the keyword lists in `scraper.py`.
4. Matching bolsas are returned with name, scientific area, deadline and link.

Results are cached for 5 minutes so repeated commands don't re-scrape.

## Tuning the keywords

Edit `CORE_KEYWORDS` / `RELATED_KEYWORDS` at the top of `scraper.py`. Write them
**lower-case and without accents** (matching is accent-insensitive). The bot
reports which keyword matched each bolsa, so you can calibrate precision.

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
