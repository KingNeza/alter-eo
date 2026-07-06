#!/usr/bin/env python3
"""
Bot de Telegram para seguimiento de proyectos personales en Google Sheets.
Diseñado para correr por CRON en GitHub Actions (sin proceso permanente).

Dos modos:
    python bot.py poll     -> revisa mensajes nuevos y actualiza la hoja
    python bot.py remind   -> manda el resumen diario a los chats registrados

El estado (offset de Telegram y chats registrados) se guarda en la propia hoja,
así que cada ejecución es independiente.

Variables de entorno (ver .env.example): BOT_TOKEN, SPREADSHEET_ID,
GOOGLE_CREDENTIALS, TIMEZONE, DUE_SOON_DAYS.
"""

import os
import sys
import json
import logging
import datetime as dt
from zoneinfo import ZoneInfo

import requests
import gspread

# --------------------------------------------------------------------------- #
# Configuración
# --------------------------------------------------------------------------- #
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger("bot-proyectos")

BOT_TOKEN = os.environ["BOT_TOKEN"]
SPREADSHEET_ID = os.environ["SPREADSHEET_ID"]
TIMEZONE = os.environ.get("TIMEZONE", "America/Mexico_City")
DUE_SOON_DAYS = int(os.environ.get("DUE_SOON_DAYS", "2"))
TZ = ZoneInfo(TIMEZONE)

API = f"https://api.telegram.org/bot{BOT_TOKEN}"

HEADERS = ["ID", "Proyecto", "Estado", "Prioridad", "Fecha límite",
           "Notas", "Creado", "Actualizado"]

ESTADOS = {"bandeja": "📥 Bandeja", "curso": "🔵 En curso",
           "pausado": "⏸️ Pausado", "hecho": "✅ Hecho"}
PRIORIDADES = {"alta": "🔴 Alta", "media": "🟡 Media", "baja": "🟢 Baja"}

# --------------------------------------------------------------------------- #
# API de Telegram (HTTP simple)
# --------------------------------------------------------------------------- #
def tg_send(chat_id, text):
    try:
        r = requests.post(f"{API}/sendMessage", json={
            "chat_id": chat_id, "text": text,
            "parse_mode": "HTML", "disable_web_page_preview": True,
        }, timeout=30)
        if not r.ok:
            log.warning("sendMessage falló (%s): %s", r.status_code, r.text[:200])
    except requests.RequestException as e:
        log.warning("Error enviando a %s: %s", chat_id, e)


def tg_get_updates(offset):
    params = {"timeout": 0, "allowed_updates": json.dumps(["message"])}
    if offset:
        params["offset"] = offset
    r = requests.get(f"{API}/getUpdates", params=params, timeout=40)
    r.raise_for_status()
    return r.json().get("result", [])


# --------------------------------------------------------------------------- #
# Google Sheets
# --------------------------------------------------------------------------- #
def _get_credentials():
    raw = os.environ.get("GOOGLE_CREDENTIALS")
    if raw:
        return json.loads(raw)
    path = os.environ.get("GOOGLE_CREDENTIALS_FILE", "credentials.json")
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def open_sheets():
    gc = gspread.service_account_from_dict(_get_credentials())
    sh = gc.open_by_key(SPREADSHEET_ID)

    try:
        ws = sh.worksheet("Proyectos")
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title="Proyectos", rows=200, cols=len(HEADERS))
    if ws.row_values(1) != HEADERS:
        ws.update([HEADERS], "A1")

    try:
        cfg = sh.worksheet("_config")
    except gspread.WorksheetNotFound:
        cfg = sh.add_worksheet(title="_config", rows=50, cols=2)
        cfg.update([["clave", "valor"]], "A1")

    try:
        chats = sh.worksheet("_chats")
    except gspread.WorksheetNotFound:
        chats = sh.add_worksheet(title="_chats", rows=50, cols=2)
        chats.update([["chat_id", "nombre"]], "A1")
    return ws, cfg, chats


# ---- estado clave/valor en _config ---------------------------------------- #
def get_config(cfg, key, default=None):
    for row in cfg.get_all_values()[1:]:
        if row and row[0] == key:
            return row[1] if len(row) > 1 else default
    return default


def set_config(cfg, key, value):
    values = cfg.get_all_values()
    for i, row in enumerate(values[1:], start=2):
        if row and row[0] == key:
            cfg.update_cell(i, 2, str(value))
            return
    cfg.append_row([key, str(value)])


# ---- chats registrados ----------------------------------------------------- #
def register_chat(chats, chat_id, nombre):
    existing = chats.col_values(1)[1:]
    if str(chat_id) not in existing:
        chats.append_row([str(chat_id), nombre])


def all_chats(chats):
    return [c for c in chats.col_values(1)[1:] if c.strip()]


# --------------------------------------------------------------------------- #
# Proyectos
# --------------------------------------------------------------------------- #
def read_projects(ws):
    projects = []
    for i, row in enumerate(ws.get_all_records(), start=2):
        row["_fila"] = i
        projects.append(row)
    return projects


def next_id(projects):
    ids = [int(p["ID"]) for p in projects if str(p["ID"]).strip().isdigit()]
    return (max(ids) + 1) if ids else 1


def find(projects, pid):
    for p in projects:
        if str(p["ID"]) == str(pid):
            return p
    return None


def today():
    return dt.datetime.now(TZ).date()


def parse_date(text):
    text = str(text).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def add_project(ws, nombre):
    projects = read_projects(ws)
    pid = next_id(projects)
    now = dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M")
    ws.append_row([pid, nombre, ESTADOS["bandeja"], "", "", "", now, now])
    return pid


def update_cell(ws, fila, colname, value):
    ws.update_cell(fila, HEADERS.index(colname) + 1, value)
    ws.update_cell(fila, HEADERS.index("Actualizado") + 1,
                   dt.datetime.now(TZ).strftime("%Y-%m-%d %H:%M"))


# --------------------------------------------------------------------------- #
# Formato
# --------------------------------------------------------------------------- #
def fmt_project_line(p):
    estado = p.get("Estado", "")
    prio = p.get("Prioridad", "")
    due = str(p.get("Fecha límite", "")).strip()
    extra = ""
    if due:
        d = parse_date(due)
        if d:
            dias = (d - today()).days
            if dias < 0:
                extra = f" — ⚠️ vencido hace {abs(dias)}d ({due})"
            elif dias == 0:
                extra = f" — ⏰ vence HOY ({due})"
            else:
                extra = f" — 📅 {due} ({dias}d)"
        else:
            extra = f" — 📅 {due}"
    prio_txt = f" [{prio}]" if prio else ""
    return f"<b>{p['ID']}</b>. {p['Proyecto']} · {estado}{prio_txt}{extra}"


def fmt_list(projects, incluir_hechos=False):
    activos = [p for p in projects
               if incluir_hechos or "Hecho" not in str(p.get("Estado", ""))]
    if not activos:
        return "No tienes proyectos activos. Mándame un texto o usa /add para agregar uno."

    def keyf(p):
        d = parse_date(p.get("Fecha límite", ""))
        return (0, (d - today()).days) if d else (1, int(p["ID"]))
    activos.sort(key=keyf)
    return "\n".join(fmt_project_line(p) for p in activos)


def build_reminder(projects):
    hoy = today()
    activos = [p for p in projects if "Hecho" not in str(p.get("Estado", ""))]
    vencidos, pronto, resto = [], [], []
    for p in activos:
        d = parse_date(p.get("Fecha límite", ""))
        if d and d < hoy:
            vencidos.append(p)
        elif d and (d - hoy).days <= DUE_SOON_DAYS:
            pronto.append(p)
        else:
            resto.append(p)

    partes = [f"☀️ <b>Buenos días. Tus proyectos ({hoy.isoformat()})</b>"]
    if vencidos:
        partes.append("\n⚠️ <b>Vencidos:</b>\n" +
                      "\n".join(fmt_project_line(p) for p in vencidos))
    if pronto:
        partes.append("\n⏰ <b>Vencen pronto:</b>\n" +
                      "\n".join(fmt_project_line(p) for p in pronto))
    if resto:
        partes.append("\n📋 <b>Activos:</b>\n" +
                      "\n".join(fmt_project_line(p) for p in resto))
    if not activos:
        partes.append("\n🎉 No tienes pendientes. ¡Bien ahí!")
    return "\n".join(partes)


# --------------------------------------------------------------------------- #
# Ruteo de comandos
# --------------------------------------------------------------------------- #
HELP = (
    "🗂️ <b>Seguimiento de proyectos</b>\n\n"
    "Mándame un texto cualquiera y lo agrego como proyecto nuevo en tu bandeja.\n\n"
    "<b>Comandos:</b>\n"
    "/add <i>nombre</i> — agregar proyecto\n"
    "/list — ver proyectos activos\n"
    "/todos — ver todos (incluye hechos)\n"
    "/curso <i>id</i> — marcar en curso\n"
    "/done <i>id</i> — marcar hecho ✅\n"
    "/pausa <i>id</i> — pausar\n"
    "/due <i>id</i> <i>fecha</i> — fecha límite (AAAA-MM-DD o DD/MM/AAAA)\n"
    "/prioridad <i>id</i> <i>alta|media|baja</i>\n"
    "/nota <i>id</i> <i>texto</i> — agregar nota\n"
    "/rename <i>id</i> <i>nombre</i> — renombrar\n"
    "/del <i>id</i> — borrar\n"
    "/resumen — recordatorio ahora mismo"
)


def handle(ws, text):
    """Recibe el texto de un mensaje y devuelve la respuesta (str)."""
    text = text.strip()
    if not text:
        return None

    if not text.startswith("/"):
        pid = add_project(ws, text)
        return (f"📥 Anotado como <b>#{pid}</b>: {text}\n"
                f"Usa /due {pid} fecha o /prioridad {pid} alta para organizarlo.")

    parts = text.split()
    cmd = parts[0].lstrip("/").split("@")[0].lower()  # quita @NombreBot
    args = parts[1:]

    if cmd in ("start", "help"):
        return HELP

    if cmd == "add":
        if not args:
            return "Uso: /add nombre del proyecto"
        nombre = " ".join(args)
        pid = add_project(ws, nombre)
        return f"✅ Agregado <b>#{pid}</b>: {nombre}"

    if cmd == "list":
        return fmt_list(read_projects(ws))
    if cmd == "todos":
        return fmt_list(read_projects(ws), incluir_hechos=True)
    if cmd == "resumen":
        return build_reminder(read_projects(ws))

    if cmd in ("done", "curso", "pausa"):
        key = {"done": "hecho", "curso": "curso", "pausa": "pausado"}[cmd]
        if not args:
            return f"Uso: /{cmd} id"
        projects = read_projects(ws)
        p = find(projects, args[0])
        if not p:
            return f"No encontré el proyecto #{args[0]}."
        update_cell(ws, p["_fila"], "Estado", ESTADOS[key])
        return f"{ESTADOS[key]} — #{args[0]} {p['Proyecto']}"

    if cmd == "due":
        if len(args) < 2:
            return "Uso: /due id AAAA-MM-DD"
        d = parse_date(args[1])
        if not d:
            return "Fecha inválida. Usa AAAA-MM-DD o DD/MM/AAAA."
        projects = read_projects(ws)
        p = find(projects, args[0])
        if not p:
            return f"No encontré el proyecto #{args[0]}."
        update_cell(ws, p["_fila"], "Fecha límite", d.isoformat())
        return f"📅 #{args[0]} vence el {d.isoformat()}"

    if cmd == "prioridad":
        if len(args) < 2 or args[1].lower() not in PRIORIDADES:
            return "Uso: /prioridad id alta|media|baja"
        projects = read_projects(ws)
        p = find(projects, args[0])
        if not p:
            return f"No encontré el proyecto #{args[0]}."
        update_cell(ws, p["_fila"], "Prioridad", PRIORIDADES[args[1].lower()])
        return f"{PRIORIDADES[args[1].lower()]} — #{args[0]} {p['Proyecto']}"

    if cmd == "nota":
        if len(args) < 2:
            return "Uso: /nota id texto de la nota"
        projects = read_projects(ws)
        p = find(projects, args[0])
        if not p:
            return f"No encontré el proyecto #{args[0]}."
        prev = str(p.get("Notas", "")).strip()
        nueva = (prev + " | " if prev else "") + f"[{today().isoformat()}] {' '.join(args[1:])}"
        update_cell(ws, p["_fila"], "Notas", nueva)
        return f"📝 Nota agregada a #{args[0]}."

    if cmd == "rename":
        if len(args) < 2:
            return "Uso: /rename id nuevo nombre"
        projects = read_projects(ws)
        p = find(projects, args[0])
        if not p:
            return f"No encontré el proyecto #{args[0]}."
        update_cell(ws, p["_fila"], "Proyecto", " ".join(args[1:]))
        return f"✏️ #{args[0]} ahora es: {' '.join(args[1:])}"

    if cmd == "del":
        if not args:
            return "Uso: /del id"
        projects = read_projects(ws)
        p = find(projects, args[0])
        if not p:
            return f"No encontré el proyecto #{args[0]}."
        ws.delete_rows(p["_fila"])
        return f"🗑️ Borrado #{args[0]}: {p['Proyecto']}"

    return f"No conozco ese comando. Escribe /help para ver la lista."


# --------------------------------------------------------------------------- #
# Modos de ejecución
# --------------------------------------------------------------------------- #
def run_poll():
    ws, cfg, chats = open_sheets()
    offset = get_config(cfg, "offset")
    offset = int(offset) if offset and str(offset).strip().isdigit() else None

    updates = tg_get_updates(offset)
    log.info("Recibidos %d updates (offset=%s)", len(updates), offset)

    last_id = offset
    for upd in updates:
        last_id = upd["update_id"]
        msg = upd.get("message")
        if not msg or "text" not in msg:
            continue
        chat_id = msg["chat"]["id"]
        user = msg.get("from", {})
        nombre = (user.get("first_name", "") + " " + user.get("last_name", "")).strip()
        register_chat(chats, chat_id, nombre or user.get("username", ""))
        try:
            reply = handle(ws, msg["text"])
        except Exception as e:
            log.exception("Error procesando mensaje")
            reply = f"⚠️ Ocurrió un error: {e}"
        if reply:
            tg_send(chat_id, reply)

    if last_id is not None:
        set_config(cfg, "offset", last_id + 1)


def run_remind():
    ws, cfg, chats = open_sheets()
    texto = build_reminder(read_projects(ws))
    destinatarios = all_chats(chats)
    log.info("Enviando resumen a %d chats", len(destinatarios))
    for chat_id in destinatarios:
        tg_send(int(chat_id), texto)


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "poll"
    if mode == "poll":
        run_poll()
    elif mode == "remind":
        run_remind()
    else:
        print("Uso: python bot.py [poll|remind]")
        sys.exit(1)


if __name__ == "__main__":
    main()
