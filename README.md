# Bolsas Bot

A Discord bot that finds **Engenharia Eletrotécnica** scholarships (bolsas) at
Instituto Superior Técnico. The `bolsas` command scrapes the
[DRH recruitment page](https://drh.tecnico.ulisboa.pt/bolseiros/recrutamento/),
opens every edital (PDF), matches the scientific area against Electrical
Engineering keywords, and replies with the matching scholarships and links.

## Commands

| Command     | Type   | What it does                                              |
|-------------|--------|-----------------------------------------------------------|
| `/bolsas`   | slash  | Lists open Electrical Engineering bolsas with edital links |
| `!bolsas`   | prefix | Same thing via a normal text message                      |

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
