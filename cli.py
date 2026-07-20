#!/usr/bin/env python3
"""Command-line interface for bolsas-bot.

bolsas/areas mirror the web console (console.py) — read the scraper directly,
no Discord round-trip. ban/unban/bans talk to Discord's REST API directly with
the bot's own token (no Gateway connection, so it never touches the running
bot process) and act with the BOT's permissions in the target guild — there is
no per-invoker Discord permission check here, unlike /ban in Discord itself.
Anyone who can run this script (SSH access to the Pi) can ban/unban.
"""
import argparse
import os
import sys
from urllib.parse import quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
import requests
import scraper

API = "https://discord.com/api/v10"
TOKEN = os.environ.get("DISCORD_TOKEN")


def _headers(reason=None):
    if not TOKEN:
        sys.exit("DISCORD_TOKEN not set (check .env)")
    h = {"Authorization": f"Bot {TOKEN}"}
    if reason:
        h["X-Audit-Log-Reason"] = quote(reason, safe="")
    return h


def _guilds():
    r = requests.get(f"{API}/users/@me/guilds", headers=_headers(), timeout=15)
    r.raise_for_status()
    return r.json()


def _resolve_guild(guild_id):
    guilds = _guilds()
    if guild_id:
        for g in guilds:
            if g["id"] == str(guild_id):
                return g
        sys.exit(f"Bot is not in a guild with id {guild_id}")
    if len(guilds) == 1:
        return guilds[0]
    if not guilds:
        sys.exit("Bot is not in any guild.")
    print("Bot is in multiple guilds, pass --guild <id>:")
    for g in guilds:
        print(f"  {g['id']}  {g['name']}")
    sys.exit(1)


# --- bolsas / areas (same scope as the web console) ---------------------------

def cmd_bolsas(args):
    area = args.area or "all"
    if area != "all" and area not in scraper.AREAS:
        sys.exit(f"Unknown area '{area}'. See: {sys.argv[0]} areas")
    if area == "all":
        bolsas = scraper.all_bolsas(force=args.refresh)
        label = "Todas as áreas"
    else:
        bolsas = scraper.search_bolsas_cached(area, force=args.refresh)
        label = scraper.area_label(area)
    print(f"{len(bolsas)} bolsa(s) para {label}\n")
    for b in bolsas:
        print(f"• [{b.score}] {b.name}")
        if b.tipo:
            print(f"    {b.tipo}" + (f" · {b.nivel}" if b.nivel else ""))
        if b.area_cientifica:
            print(f"    Área: {b.area_cientifica}")
        if b.prazo:
            print(f"    Prazo: {b.prazo}")
        print(f"    {b.pdf_url}\n")


def cmd_areas(args):
    for k in scraper.list_areas():
        print(f"{k:15s} {scraper.area_label(k)}")


# --- ban / unban / bans (bot's own permissions, no per-user gate) -------------

def cmd_ban(args):
    guild = _resolve_guild(args.guild)
    if not args.yes:
        ans = input(f"Ban user {args.user_id} from '{guild['name']}'? [y/N] ").strip().lower()
        if ans != "y":
            return print("Cancelled.")
    r = requests.put(f"{API}/guilds/{guild['id']}/bans/{args.user_id}",
                     headers=_headers(args.reason or "cli"),
                     json={"delete_message_seconds": 0}, timeout=15)
    if r.status_code == 204:
        print(f"Banned {args.user_id} from {guild['name']}.")
    else:
        sys.exit(f"Ban failed: {r.status_code} {r.text}")


def cmd_unban(args):
    guild = _resolve_guild(args.guild)
    if not args.yes:
        ans = input(f"Unban user {args.user_id} from '{guild['name']}'? [y/N] ").strip().lower()
        if ans != "y":
            return print("Cancelled.")
    r = requests.delete(f"{API}/guilds/{guild['id']}/bans/{args.user_id}",
                        headers=_headers("cli"), timeout=15)
    if r.status_code == 204:
        print(f"Unbanned {args.user_id} from {guild['name']}.")
    else:
        sys.exit(f"Unban failed: {r.status_code} {r.text}")


def cmd_bans(args):
    guild = _resolve_guild(args.guild)
    r = requests.get(f"{API}/guilds/{guild['id']}/bans?limit=1000", headers=_headers(), timeout=15)
    if r.status_code == 403:
        sys.exit(f"Forbidden: the bot doesn't have the 'Ban Members' permission in {guild['name']!r}.")
    r.raise_for_status()
    entries = r.json()
    if not entries:
        return print(f"No bans in {guild['name']}.")
    for e in entries:
        u = e["user"]
        tag = u.get("username", "?")
        print(f"{u['id']}  {tag}" + (f"  ({e['reason']})" if e.get("reason") else ""))


def main():
    p = argparse.ArgumentParser(description="bolsas-bot CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bolsas", help="List open bolsas for an area")
    b.add_argument("area", nargs="?", help="Area key (see 'areas'), default: all")
    b.add_argument("--refresh", action="store_true", help="Bypass the 5-minute cache")
    b.set_defaults(func=cmd_bolsas)

    sub.add_parser("areas", help="List available areas").set_defaults(func=cmd_areas)

    ban = sub.add_parser("ban", help="Ban a Discord user from the server")
    ban.add_argument("user_id")
    ban.add_argument("--reason")
    ban.add_argument("--guild", help="Guild ID (only needed if the bot is in more than one)")
    ban.add_argument("-y", "--yes", action="store_true", help="Skip confirmation")
    ban.set_defaults(func=cmd_ban)

    unban = sub.add_parser("unban", help="Unban a Discord user by ID")
    unban.add_argument("user_id")
    unban.add_argument("--guild")
    unban.add_argument("-y", "--yes", action="store_true")
    unban.set_defaults(func=cmd_unban)

    bans = sub.add_parser("bans", help="List current bans")
    bans.add_argument("--guild")
    bans.set_defaults(func=cmd_bans)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
