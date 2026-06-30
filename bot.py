"""
Discord bot exposing the `bolsas` command.

`/bolsas` (slash) or `!bolsas` (prefix) scrapes the IST recruitment page,
opens every edital, and replies with the scholarships matching the Electrical
Engineering area (Engenharia Eletrotecnica) and links to each one.

Run:  python bot.py   (needs DISCORD_TOKEN in the environment or a .env file)
"""

from __future__ import annotations

import asyncio
import os
import sys

import discord
from discord.ext import commands

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import scraper

# Flush stdout immediately so startup logs appear in real time on host consoles
# (otherwise print() is block-buffered when output isn't a terminal).
sys.stdout.reconfigure(line_buffering=True)

TOKEN = os.environ.get("DISCORD_TOKEN")
COMMAND_PREFIX = os.environ.get("COMMAND_PREFIX", "!")
EMBED_COLOR = 0x2D7FF9

intents = discord.Intents.default()
intents.message_content = True  # required for the !prefix command
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)


def build_embeds(bolsas: list[scraper.Bolsa]) -> list[discord.Embed]:
    """Render results as one or more embeds (Discord caps fields at 25/embed)."""
    if not bolsas:
        return [discord.Embed(
            title="Bolsas — Engenharia Eletrotécnica",
            description=("Nenhuma bolsa para a área de Engenharia Eletrotécnica "
                         "encontrada de momento.\n"
                         f"Fonte: {scraper.LISTING_URL}"),
            color=EMBED_COLOR,
        )]

    embeds: list[discord.Embed] = []
    for i in range(0, len(bolsas), 25):
        chunk = bolsas[i:i + 25]
        embed = discord.Embed(
            title="Bolsas — Engenharia Eletrotécnica",
            description=f"{len(bolsas)} bolsa(s) encontrada(s) · fonte: "
                        f"[DRH IST]({scraper.LISTING_URL})",
            color=EMBED_COLOR,
        )
        for b in chunk:
            value_lines = []
            tipo_line = b.tipo or "Bolsa de Investigação"
            if b.nivel:
                tipo_line += f" · 🎓 {b.nivel}"
            value_lines.append(f"🏷️ {tipo_line}")
            if b.area_cientifica:
                value_lines.append(f"📚 {b.area_cientifica}")
            if b.prazo:
                value_lines.append(f"⏳ Prazo: **{b.prazo}**")
            value_lines.append(f"🔗 [Abrir edital]({b.pdf_url})")
            name = b.name if len(b.name) <= 256 else b.name[:253] + "..."
            embed.add_field(name=f"📄 {name}", value="\n".join(value_lines),
                            inline=False)
        embeds.append(embed)
    return embeds


async def run_search() -> list[scraper.Bolsa]:
    # The scrape is blocking (network + PDF parsing); keep the event loop free.
    return await asyncio.to_thread(scraper.search_bolsas_cached)


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Logged in as {bot.user} · synced {len(synced)} slash command(s)")
    except Exception as exc:  # pragma: no cover
        print(f"Logged in as {bot.user} · slash sync failed: {exc}")


@bot.tree.command(name="bolsas",
                  description="Bolsas de Engenharia Eletrotécnica abertas no IST")
async def bolsas_slash(interaction: discord.Interaction):
    await interaction.response.defer(thinking=True)
    try:
        bolsas = await run_search()
        for embed in build_embeds(bolsas):
            await interaction.followup.send(embed=embed)
    except Exception as exc:
        await interaction.followup.send(f"⚠️ Erro ao procurar bolsas: `{exc}`")


@bot.command(name="bolsas")
async def bolsas_prefix(ctx: commands.Context):
    async with ctx.typing():
        try:
            bolsas = await run_search()
            for embed in build_embeds(bolsas):
                await ctx.send(embed=embed)
        except Exception as exc:
            await ctx.send(f"⚠️ Erro ao procurar bolsas: `{exc}`")


def main():
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN not set. Put it in a .env file or your environment.\n"
            "See .env.example."
        )
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
