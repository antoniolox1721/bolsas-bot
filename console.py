#!/usr/bin/env python3
"""Web console for bolsas-bot.

Bolsas search (bolsas/refresh) calls scraper.py directly, no Discord round
trip. Moderation (ban/unban/bans) talks to Discord's REST API directly with
the bot's own token (no Gateway connection, so it never touches the running
bot process) -- same approach as cli.py, just with a form instead of a
terminal. Deliberately excludes apply/fenix/ant: those handle credentials, an
irreversible submission, or an admin-role grant, and stay Discord-DM-only by
design (same boundary the bot itself already enforces).

No per-visitor auth here (matches every other tile on the LAN/Tailscale-only
dashboard this sits behind) -- ban/unban ask for a JS confirmation before
submitting as a fat-finger guard, same idea as cli.py's y/N prompt.
"""
import html
import os
import shlex
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass
import requests
import scraper

PORT = int(os.environ.get("CONSOLE_PORT", "5005"))
API = "https://discord.com/api/v10"
TOKEN = os.environ.get("DISCORD_TOKEN")

PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>Bolsas Bot Console</title>
<style>
body {{ font-family: system-ui, sans-serif; max-width: 760px; margin: 2rem auto; padding: 0 1rem;
       background: #14161a; color: #e7e9ec; }}
h1 {{ font-size: 1.3rem; }}
h2 {{ font-size: 1.05rem; margin-top: 2.5rem; border-top: 1px solid #2a2e35; padding-top: 1.5rem; }}
form {{ display: flex; gap: .5rem; margin-bottom: 1.5rem; flex-wrap: wrap; align-items: center; }}
select, button, input {{ font-size: 1rem; padding: .4rem .6rem; border-radius: 6px; border: 1px solid #3a3f47;
                  background: #1e2126; color: #e7e9ec; }}
input {{ flex: 1; min-width: 140px; }}
button {{ cursor: pointer; background: #2d7ff9; border-color: #2d7ff9; color: white; }}
button:hover {{ background: #1e6fe0; }}
button.danger {{ background: #c0392b; border-color: #c0392b; }}
button.danger:hover {{ background: #a5321f; }}
.card {{ border: 1px solid #2a2e35; border-radius: 8px; padding: .8rem 1rem; margin-bottom: .8rem;
        background: #1a1d22; }}
.card h3 {{ margin: 0 0 .4rem; font-size: 1.05rem; }}
.card p {{ margin: .2rem 0; font-size: .92rem; color: #c4c8ce; }}
.card a {{ color: #6fa8ff; }}
.err {{ color: #ff6b6b; }}
.ok {{ color: #6fcf97; }}
.meta {{ color: #9aa0a8; font-size: .9rem; margin-bottom: .8rem; }}
table {{ width: 100%; border-collapse: collapse; font-size: .92rem; }}
td {{ padding: .3rem .4rem; border-bottom: 1px solid #2a2e35; }}
#term-log {{ background: #0d0f12; border: 1px solid #2a2e35; border-radius: 8px; padding: .8rem 1rem;
            max-height: 340px; overflow-y: auto; white-space: pre-wrap; font-family: ui-monospace, monospace;
            font-size: .88rem; margin-bottom: .5rem; }}
#term-input {{ width: 100%; font-family: ui-monospace, monospace; box-sizing: border-box; }}
</style></head>
<body>
<h1>🎓 Bolsas Bot — Console</h1>

<h2>Linha de comandos</h2>
<pre id="term-log">bolsas-bot cli — escreve 'help' para a lista de comandos, Enter para executar</pre>
<input id="term-input" placeholder="ex: bolsas eletrotecnica  ·  ban 123456 --reason spam  ·  bans">
<script>
async function termRun(e) {{
  if (e.key !== 'Enter') return;
  var input = document.getElementById('term-input');
  var cmd = input.value.trim();
  if (!cmd) return;
  var log = document.getElementById('term-log');
  log.textContent += '\\n$ ' + cmd + '\\n';
  input.value = '';
  var first = cmd.split(/\\s+/)[0].toLowerCase();
  if ((first === 'ban' || first === 'unban') && !confirm(cmd + ' ?')) {{
    log.textContent += '(cancelado)\\n';
    log.scrollTop = log.scrollHeight;
    return;
  }}
  input.disabled = true;
  try {{
    var res = await fetch('/cmd', {{method: 'POST', headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
                                    body: 'cmd=' + encodeURIComponent(cmd)}});
    log.textContent += (await res.text()) + '\\n';
  }} catch (err) {{
    log.textContent += 'erro: ' + err + '\\n';
  }}
  input.disabled = false;
  input.focus();
  log.scrollTop = log.scrollHeight;
}}
document.getElementById('term-input').addEventListener('keydown', termRun);
</script>

<h2>Bolsas</h2>
<form method="post" action="/run">
  <select name="action">
    <option value="bolsas">bolsas</option>
    <option value="refresh">refresh (ignora cache de 5 min)</option>
  </select>
  <select name="area">
    <option value="all">Todas as áreas</option>
    {area_options}
  </select>
  <button type="submit">Run</button>
</form>
{results}

<h2>Moderação</h2>
<form method="post" action="/mod" onsubmit="return modConfirm(this)">
  <select name="guild">
    {guild_options}
  </select>
  <select name="mod_action" onchange="modToggle(this)">
    <option value="list">listar banidos</option>
    <option value="ban">ban</option>
    <option value="unban">unban</option>
  </select>
  <input type="text" name="user_id" placeholder="ID do utilizador" id="mod-user">
  <input type="text" name="reason" placeholder="motivo (opcional, só ban)" id="mod-reason">
  <button type="submit" class="danger" id="mod-submit">Run</button>
</form>
{mod_results}

<script>
function modToggle(sel) {{
  var needsUser = sel.value !== 'list';
  document.getElementById('mod-user').style.display = needsUser ? '' : 'none';
  document.getElementById('mod-reason').style.display = sel.value === 'ban' ? '' : 'none';
}}
function modConfirm(form) {{
  var action = form.mod_action.value;
  if (action === 'list') return true;
  var uid = form.user_id.value.trim();
  if (!uid) {{ alert('Indica o ID do utilizador.'); return false; }}
  return confirm(action + ' user ' + uid + '?');
}}
modToggle(document.querySelector('select[name=mod_action]'));
</script>
</body></html>
"""


# --- bolsas -------------------------------------------------------------------

def area_options_html(selected=None):
    opts = []
    for key in scraper.list_areas():
        label = scraper.area_label(key)
        sel = " selected" if key == selected else ""
        opts.append(f'<option value="{html.escape(key)}"{sel}>{html.escape(label)}</option>')
    return "\n".join(opts)


def render_bolsas(bolsas, label):
    meta = f'<p class="meta">{len(bolsas)} bolsa(s) para <b>{html.escape(label)}</b> · ' \
           f'<a href="{html.escape(scraper.URL)}" target="_blank">DRH IST</a></p>'
    if not bolsas:
        return meta
    cards = []
    for b in bolsas:
        parts = [f"<h3>{html.escape(b.name)}</h3>"]
        if b.tipo:
            parts.append(f"<p>🏷️ {html.escape(b.tipo)}" +
                         (f" · 🎓 {html.escape(b.nivel)}" if b.nivel else "") + "</p>")
        if b.area_cientifica:
            parts.append(f"<p>📚 {html.escape(b.area_cientifica)}</p>")
        if b.avaliacao:
            parts.append(f"<p>📝 {html.escape(b.avaliacao[:200])}</p>")
        if b.prazo:
            parts.append(f"<p>⏳ Prazo: <b>{html.escape(b.prazo)}</b></p>")
        if b.pdf_url:
            parts.append(f'<p>🔗 <a href="{html.escape(b.pdf_url)}" target="_blank">Abrir edital</a></p>')
        cards.append("<div class='card'>" + "\n".join(parts) + "</div>")
    return meta + "\n".join(cards)


# --- moderation (Discord REST, same approach as cli.py) -----------------------

def _headers(reason=None):
    h = {"Authorization": f"Bot {TOKEN}"}
    if reason:
        h["X-Audit-Log-Reason"] = quote(reason, safe="")
    return h


_guilds_cache = None  # (timestamp, list) -- /users/@me/guilds rate-limits hard,
                      # and every page load + every /cmd + /mod call needs it


def _guilds():
    global _guilds_cache
    if not TOKEN:
        return []
    now = time.time()
    if _guilds_cache and now - _guilds_cache[0] < 30:
        return _guilds_cache[1]
    r = requests.get(f"{API}/users/@me/guilds", headers=_headers(), timeout=15)
    r.raise_for_status()
    data = r.json()
    _guilds_cache = (now, data)
    return data


def guild_options_html(selected=None):
    if not TOKEN:
        return '<option value="">DISCORD_TOKEN não definido</option>'
    try:
        guilds = _guilds()
    except Exception as ex:
        return f'<option value="">erro: {html.escape(str(ex))}</option>'
    if not guilds:
        return '<option value="">o bot não está em nenhum servidor</option>'
    opts = []
    for g in guilds:
        sel = " selected" if g["id"] == selected else ""
        opts.append(f'<option value="{html.escape(g["id"])}"{sel}>{html.escape(g["name"])}</option>')
    return "\n".join(opts)


def _guild_name(guild_id, guilds):
    for g in guilds:
        if g["id"] == guild_id:
            return g["name"]
    return guild_id


def render_mod(mod_action, guild_id, user_id, reason):
    if not TOKEN:
        return '<p class="err">DISCORD_TOKEN não definido.</p>'
    try:
        guilds = _guilds()
    except Exception as ex:
        return f'<p class="err">Erro a listar servidores: {html.escape(str(ex))}</p>'
    if not guild_id:
        return '<p class="err">Escolhe um servidor.</p>'
    name = _guild_name(guild_id, guilds)

    if mod_action == "list":
        r = requests.get(f"{API}/guilds/{guild_id}/bans?limit=1000", headers=_headers(), timeout=15)
        if r.status_code == 403:
            return f'<p class="err">O bot não tem a permissão <b>Ban Members</b> em {html.escape(name)}.</p>'
        if r.status_code != 200:
            return f'<p class="err">Erro {r.status_code}: {html.escape(r.text[:300])}</p>'
        entries = r.json()
        if not entries:
            return f'<p class="meta">Não há ninguém banido em {html.escape(name)}.</p>'
        rows = "".join(
            f"<tr><td>{html.escape(e['user']['id'])}</td>"
            f"<td>{html.escape(e['user'].get('username', '?'))}</td>"
            f"<td>{html.escape(e.get('reason') or '')}</td></tr>"
            for e in entries)
        return f'<p class="meta">{len(entries)} banido(s) em {html.escape(name)}</p><table>{rows}</table>'

    if not user_id or not user_id.isdigit():
        return '<p class="err">ID de utilizador inválido.</p>'

    if mod_action == "ban":
        r = requests.put(f"{API}/guilds/{guild_id}/bans/{user_id}",
                         headers=_headers(reason or "web console"),
                         json={"delete_message_seconds": 0}, timeout=15)
        if r.status_code == 204:
            return f'<p class="ok">🔨 {html.escape(user_id)} banido de {html.escape(name)}.</p>'
        if r.status_code == 403:
            return f'<p class="err">O bot não tem a permissão <b>Ban Members</b> em {html.escape(name)}.</p>'
        return f'<p class="err">Falhou ({r.status_code}): {html.escape(r.text[:300])}</p>'

    if mod_action == "unban":
        r = requests.delete(f"{API}/guilds/{guild_id}/bans/{user_id}",
                            headers=_headers("web console"), timeout=15)
        if r.status_code == 204:
            return f'<p class="ok">✅ {html.escape(user_id)} desbanido de {html.escape(name)}.</p>'
        if r.status_code == 403:
            return f'<p class="err">O bot não tem a permissão <b>Ban Members</b> em {html.escape(name)}.</p>'
        return f'<p class="err">Falhou ({r.status_code}): {html.escape(r.text[:300])}</p>'

    return '<p class="err">Ação desconhecida.</p>'


# --- command line (terminal-style, mirrors cli.py's argument syntax) ---------

def _popflag(tokens, flag, takes_value=True):
    if flag not in tokens:
        return None
    i = tokens.index(flag)
    if takes_value:
        if i + 1 >= len(tokens):
            del tokens[i]
            return None
        val = tokens[i + 1]
        del tokens[i:i + 2]
        return val
    del tokens[i]
    return True


def run_command_line(command_str):
    try:
        tokens = shlex.split(command_str)
    except ValueError as ex:
        return f"error: {ex}"
    if not tokens:
        return ""
    cmd, rest = tokens[0].lower(), tokens[1:]

    if cmd == "help":
        return ("commands:\n"
                "  bolsas [area] [--refresh]\n"
                "  refresh [area]\n"
                "  areas\n"
                "  bans [--guild ID]\n"
                "  ban <user_id> [--reason TEXT] [--guild ID]\n"
                "  unban <user_id> [--guild ID]")

    if cmd in ("bolsas", "refresh"):
        force = cmd == "refresh" or bool(_popflag(rest, "--refresh", takes_value=False))
        area = rest[0] if rest else "all"
        if area != "all" and area not in scraper.AREAS:
            return f"unknown area '{area}'. try: areas"
        if area == "all":
            bolsas, label = scraper.all_bolsas(force=force), "Todas as áreas"
        else:
            bolsas, label = scraper.search_bolsas_cached(area, force=force), scraper.area_label(area)
        lines = [f"{len(bolsas)} bolsa(s) para {label}", ""]
        for b in bolsas:
            lines.append(f"[{b.score}] {b.name}")
            if b.tipo:
                lines.append(f"    {b.tipo}" + (f" · {b.nivel}" if b.nivel else ""))
            if b.prazo:
                lines.append(f"    Prazo: {b.prazo}")
            lines.append(f"    {b.pdf_url}")
        return "\n".join(lines)

    if cmd == "areas":
        return "\n".join(f"{k:15s} {scraper.area_label(k)}" for k in scraper.list_areas())

    if cmd in ("ban", "unban", "bans"):
        if not TOKEN:
            return "error: DISCORD_TOKEN not set"
        guild_id = _popflag(rest, "--guild")
        reason = _popflag(rest, "--reason") if cmd == "ban" else None
        try:
            guilds = _guilds()
        except Exception as ex:
            return f"error listing guilds: {ex}"
        if not guild_id:
            if len(guilds) == 1:
                guild_id = guilds[0]["id"]
            elif not guilds:
                return "error: bot is not in any guild"
            else:
                return "bot is in multiple guilds, pass --guild <id>:\n" + \
                       "\n".join(f"  {g['id']}  {g['name']}" for g in guilds)
        name = _guild_name(guild_id, guilds)

        if cmd == "bans":
            r = requests.get(f"{API}/guilds/{guild_id}/bans?limit=1000", headers=_headers(), timeout=15)
            if r.status_code == 403:
                return f"error: bot lacks Ban Members in {name}"
            if r.status_code != 200:
                return f"error {r.status_code}: {r.text[:300]}"
            entries = r.json()
            if not entries:
                return f"no bans in {name}"
            return "\n".join(f"{e['user']['id']}  {e['user'].get('username', '?')}" +
                             (f"  ({e['reason']})" if e.get("reason") else "") for e in entries)

        if not rest or not rest[0].isdigit():
            usage = f"usage: {cmd} <user_id>" + (" [--reason TEXT]" if cmd == "ban" else "") + " [--guild ID]"
            return usage
        user_id = rest[0]

        if cmd == "ban":
            r = requests.put(f"{API}/guilds/{guild_id}/bans/{user_id}",
                             headers=_headers(reason or "web console cli"),
                             json={"delete_message_seconds": 0}, timeout=15)
            if r.status_code == 204:
                return f"banned {user_id} from {name}"
            if r.status_code == 403:
                return f"error: bot lacks Ban Members in {name}"
            return f"error {r.status_code}: {r.text[:300]}"

        r = requests.delete(f"{API}/guilds/{guild_id}/bans/{user_id}",
                            headers=_headers("web console cli"), timeout=15)
        if r.status_code == 204:
            return f"unbanned {user_id} from {name}"
        if r.status_code == 403:
            return f"error: bot lacks Ban Members in {name}"
        return f"error {r.status_code}: {r.text[:300]}"

    return f"unknown command: {cmd} (try 'help')"


# --- server ---------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def _send(self, body, code=200, content_type="text/html; charset=utf-8"):
        b = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def _render(self, results="", mod_results="", area=None, guild=None):
        self._send(PAGE.format(area_options=area_options_html(area), results=results,
                               guild_options=guild_options_html(guild), mod_results=mod_results))

    def do_GET(self):
        if self.path != "/":
            return self._send("Not found", 404)
        self._render()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8")
        fields = parse_qs(body)

        if self.path == "/run":
            action = (fields.get("action") or ["bolsas"])[0]
            area = (fields.get("area") or ["all"])[0]
            force = action == "refresh"
            try:
                if area == "all":
                    bolsas = scraper.all_bolsas(force)
                    label = "Todas as áreas"
                else:
                    if area not in scraper.AREAS:
                        raise ValueError("área desconhecida")
                    bolsas = scraper.search_bolsas_cached(area, force)
                    label = scraper.area_label(area)
                results = render_bolsas(bolsas, label)
            except Exception as ex:
                results = f"<p class='err'>Erro: {html.escape(str(ex))}</p>"
            return self._render(results=results, area=area)

        if self.path == "/cmd":
            cmd = (fields.get("cmd") or [""])[0]
            try:
                out = run_command_line(cmd)
            except Exception as ex:
                out = f"error: {ex}"
            return self._send(out, content_type="text/plain; charset=utf-8")

        if self.path == "/mod":
            mod_action = (fields.get("mod_action") or ["list"])[0]
            guild_id = (fields.get("guild") or [""])[0]
            user_id = (fields.get("user_id") or [""])[0].strip()
            reason = (fields.get("reason") or [""])[0].strip()
            mod_results = render_mod(mod_action, guild_id, user_id, reason)
            return self._render(mod_results=mod_results, guild=guild_id)

        return self._send("Not found", 404)

    def log_message(self, fmt, *args):
        print(f"[console] {self.address_string()} " + (fmt % args), flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Bolsas console listening on :{PORT}", flush=True)
    server.serve_forever()
