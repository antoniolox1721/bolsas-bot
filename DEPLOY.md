# Hosting the bot for free (24/7, off your PC)

Goal: the bot stays online without your computer, costs nothing, and is easy to
update. As of 2026 the old go-to free tiers (Railway, Fly.io) are gone, so the
best free + low-effort option for a Discord bot is a **Pterodactyl-based free
bot panel**. Recommended: **[Bot-Hosting.net](https://bot-hosting.net)** (no
credit card, 24/7 no-sleep, auto-restart, web file editor, env-var manager,
GitHub integration). Wispbyte and HeavenCloud are equivalent alternatives.

A Discord bot keeps a permanent connection to Discord, so it needs an
always-on process. That's why "serverless"/sleep-on-idle free tiers (Vercel,
Render free web services) do **not** work here — these bot panels do.

---

## Option A — Bot-Hosting.net, no Git (simplest)

1. Sign up at <https://bot-hosting.net> (Discord login, no card).
2. **Create Server → Python.**
3. Open the server's **File Manager** and upload these files (keep the layout):
   `bot.py`, `scraper.py`, `requirements.txt`, and the `assets/` folder.
   (You can drag-and-drop, or upload a zip and unzip it in the panel.)
4. **Startup tab:**
   - Set the app/Python file to **`bot.py`**.
   - Make sure dependencies install on boot. Either set the panel's
     "requirements file" to `requirements.txt`, or set the startup command to:
     ```
     pip install -r requirements.txt && python bot.py
     ```
5. **Startup → Variables (or Environment):** add a variable
   `DISCORD_TOKEN` = your bot token from the Discord Developer Portal.
6. Click **Start**. Watch the **Console** — you should see
   `Logged in as <bot> · synced 1 slash command(s)`.

### Making changes later (no Git)
Edit the file in the panel's **web editor** (or re-upload it), then click
**Restart**. Done — nothing on your PC required.

---

## Option B — Bot-Hosting.net + GitHub (versioned, still simple)

This keeps a backup/history and makes updates a 2-click pull. The repo is
already initialized locally (`git` is set up in this folder).

1. Create an empty GitHub repo and push this project to it:
   ```bash
   gh repo create bolsas-bot --private --source=. --remote=origin --push
   # or, without gh:
   # git remote add origin https://github.com/<you>/bolsas-bot.git
   # git push -u origin master
   ```
   `.env` is git-ignored, so your token never lands in the repo.
2. In the panel, use **GitHub integration** (Startup/Git tab) to point the
   server at your repo. Set the run file to `bot.py`, requirements to
   `requirements.txt`, and add the `DISCORD_TOKEN` variable as in Option A.
3. Start the server.

### Making changes later (Git)
```bash
# edit code locally, then:
git add -A && git commit -m "tweak keywords"
git push
```
Then in the panel click **Pull** (or it auto-pulls) and **Restart**.

> Tip: the keyword lists you'll most often tweak live at the top of
> `scraper.py` (`CORE_KEYWORDS` / `RELATED_KEYWORDS`).

---

## Option C — Oracle Cloud Always Free (truly free forever, more setup)

Only if you want full control and don't mind a one-time setup. You get a small
always-free ARM VM; run the bot as a service so it survives reboots.

```bash
# on the VM (Ubuntu), one time:
sudo apt update && sudo apt install -y python3-venv git
git clone <your-repo-url> bolsas-bot && cd bolsas-bot
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
printf 'DISCORD_TOKEN=your-token\n' > .env

# run it 24/7 with systemd:
sudo tee /etc/systemd/system/bolsas-bot.service >/dev/null <<EOF
[Unit]
Description=Bolsas Discord bot
After=network-online.target

[Service]
WorkingDirectory=$HOME/bolsas-bot
ExecStart=$HOME/bolsas-bot/.venv/bin/python bot.py
Restart=always
User=$USER

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable --now bolsas-bot
```

Update later: `git pull && sudo systemctl restart bolsas-bot`.

---

## Notes that apply to any host

- The bot needs the **Message Content Intent** enabled in the Discord Developer
  Portal only for the `!bolsas` text command. The `/bolsas` slash command works
  without it.
- Resource use is tiny: it idles near-zero and only scrapes when someone runs
  the command (results are cached 5 min). 128 MB RAM is plenty.
- Never commit or paste your token anywhere public. If it leaks, regenerate it
  in the Developer Portal.
