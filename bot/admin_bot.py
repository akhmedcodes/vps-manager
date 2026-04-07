#!/usr/bin/env python3
"""
vps-manager/bot/admin_bot.py
─────────────────────────────────────────────────────────────────
Telegram admin panel for VPS Manager.
Uses aiogram 2.x (2.25.1).

Install aiogram into your venv:
  <your_python> -m pip install aiogram==2.25.1

Features:
  /start      main menu
  /status     all services
  /monitor    PNG dashboard (needs matplotlib)
  /projects   inline project management
  /ssl        certificate status
  /renew      renew all LE certs
  /system     CPU / mem / disk
  /logs       per-service logs
  Auto-alert  polls every 60s, alerts on crash
"""

import asyncio
import logging
import os
import sys
import tempfile
import time

# ── resolve project root regardless of where the script lives ─────────────────
BOT_DIR  = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.dirname(BOT_DIR)
sys.path.insert(0, BASE_DIR)

from utils import config as cfg_mod
from utils import systemctl as svc_mod
from utils import monitor as mon_mod
from utils import ssl as ssl_mod
from utils import logger as log_mod


# ── aiogram 2.x ───────────────────────────────────────────────────────────────
try:
    from aiogram import Bot, Dispatcher, executor, types
    from aiogram.types import (
        InlineKeyboardMarkup, InlineKeyboardButton,
        ReplyKeyboardMarkup, KeyboardButton,
        ParseMode, InputFile,
    )
    from aiogram.dispatcher.filters import Text
    from aiogram.utils.exceptions import BotBlocked, ChatNotFound
except ImportError:
    python = sys.executable
    print(f"aiogram not installed.\nRun: {python} -m pip install aiogram==2.25.1")
    sys.exit(1)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("vps-bot")

# ── config ────────────────────────────────────────────────────────────────────
_config   = cfg_mod.load_config()
_bot_cfg  = cfg_mod.get_bot_config(_config)
BOT_TOKEN = _bot_cfg.get("token", "")
ADMIN_IDS = set(int(x) for x in _bot_cfg.get("admin_ids", []))

if not BOT_TOKEN:
    print("Bot token not configured.  Set it via the TUI:  t → Configure bot token")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
dp  = Dispatcher(bot)

_alerted: dict = {}   # project_name → last_alert_timestamp


# ─── Auth ─────────────────────────────────────────────────────────────────────

def admin_only(handler):
    async def wrapper(message: types.Message, *args, **kwargs):
        if message.from_user.id not in ADMIN_IDS:
            await message.reply("Access denied.")
            return

        return await handler(message, *args, **kwargs)
    wrapper.__name__ = handler.__name__
    return wrapper


def admin_only_cb(handler):
    async def wrapper(call: types.CallbackQuery, *a, **kw):
        if call.from_user.id not in ADMIN_IDS:
            await call.answer("Access denied.", show_alert=True)
            return
        return await handler(call, *a, **kw)
    wrapper.__name__ = handler.__name__
    return wrapper


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _cfg():
    return cfg_mod.load_config()

def _projects(config=None):
    return (config or _cfg()).get("projects", [])

def _emoji(state: str) -> str:
    s = state.lower()
    if s == "active":   return "🟢"
    if s == "failed":   return "🔴"
    if s == "inactive": return "⚪"
    return "🟡"

def _svc_line(p: dict) -> str:
    name  = p["name"]
    state = svc_mod.get_service_status(name)["state"] \
            if svc_mod.unit_file_exists(name) else "no-unit"
    return (f"{_emoji(state)} <b>{name}</b>  "
            f"<code>[{p.get('type','?')}]</code>  "
            f"port:{p.get('port','—')}  <i>{state}</i>")


# ─── Keyboards ────────────────────────────────────────────────────────────────

def _main_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add(
        KeyboardButton("📋 Projects"),
        KeyboardButton("📊 Monitor"),
        KeyboardButton("🔒 SSL"),
        KeyboardButton("📜 Logs"),
        KeyboardButton("ℹ️ System"),
        KeyboardButton("🔄 Renew SSL"),
    )
    return kb


def _projects_kb(prefix="proj") -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=1)
    for p in _projects():
        name  = p["name"]
        state = svc_mod.get_service_status(name)["state"] \
                if svc_mod.unit_file_exists(name) else "no-unit"
        kb.add(InlineKeyboardButton(
            f"{_emoji(state)} {name}",
            callback_data=f"{prefix}:{name}",
        ))
    return kb


def _actions_kb(name: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(row_width=3)
    kb.add(
        InlineKeyboardButton("▶ Start",    callback_data=f"svc_start:{name}"),
        InlineKeyboardButton("⏹ Stop",     callback_data=f"svc_stop:{name}"),
        InlineKeyboardButton("🔄 Restart", callback_data=f"svc_restart:{name}"),
    )
    kb.add(
        InlineKeyboardButton("📜 Logs",    callback_data=f"svc_logs:{name}"),
        InlineKeyboardButton("📊 Metrics", callback_data=f"svc_metrics:{name}"),
        InlineKeyboardButton("⬅ Back",    callback_data="proj_list"),
    )
    return kb


# ─── /start ───────────────────────────────────────────────────────────────────

@dp.message_handler(commands=["start"])
@admin_only
async def cmd_start(msg: types.Message, **kwargs):
    projects = _projects()
    n_ok = sum(
        1 for p in projects
        if svc_mod.unit_file_exists(p["name"]) and
           svc_mod.get_service_status(p["name"])["state"] == "active"
    )
    await msg.reply(
        f"<b>VPS Manager Bot</b>\n\n"
        f"Services: <b>{n_ok}/{len(projects)}</b> active\n"
        f"Uptime: <code>{mon_mod.uptime_str()}</code>\n\n"
        f"Use the menu or /help for commands.",
        reply_markup=_main_kb(),
    )


@dp.message_handler(commands=["help"])
@admin_only
async def cmd_help(msg: types.Message, **kwargs):
    await msg.reply(
        "<b>Commands</b>\n"
        "/start — main menu\n"
        "/status — all services\n"
        "/monitor — dashboard PNG\n"
        "/projects — manage projects\n"
        "/ssl — SSL status\n"
        "/renew — renew all certs\n"
        "/logs &lt;name&gt; — service logs\n"
        "/system — CPU / MEM / disk\n"
    )


# ─── /status ──────────────────────────────────────────────────────────────────

@dp.message_handler(commands=["status"])
@dp.message_handler(Text(equals="📋 Projects"))
@admin_only
async def cmd_status(msg: types.Message, **kwargs):
    projects = _projects()
    if not projects:
        await msg.reply("No projects configured.")
        return
    lines = ["<b>Service Status</b>\n"] + [_svc_line(p) for p in projects]
    await msg.reply("\n".join(lines), reply_markup=_projects_kb())


# ─── /system ──────────────────────────────────────────────────────────────────

@dp.message_handler(commands=["system"])
@dp.message_handler(Text(equals="ℹ️ System"))
@admin_only
async def cmd_system(msg: types.Message, **kwargs):
    cpu  = mon_mod.cpu_percent()
    mem  = mon_mod.memory_info()
    disk = mon_mod.disk_info()
    la   = mon_mod.load_avg()
    up   = mon_mod.uptime_str()
    await msg.reply(
        f"<b>System Snapshot</b>\n\n"
        f"⏱ Uptime:  <code>{up}</code>\n"
        f"⚙️ Load:    <code>{la[0]:.2f}  {la[1]:.2f}  {la[2]:.2f}</code>\n\n"
        f"🖥 CPU:     <code>{cpu:.1f}%</code>\n"
        f"🧠 Memory:  <code>{mem['used_mb']:.0f}/{mem['total_mb']:.0f} MB ({mem['percent']:.0f}%)</code>\n"
        f"💾 Disk:    <code>{disk['used_gb']:.1f}/{disk['total_gb']:.1f} GB ({disk['percent']:.0f}%)</code>\n"
    )


# ─── /monitor ─────────────────────────────────────────────────────────────────

@dp.message_handler(commands=["monitor"])
@dp.message_handler(Text(equals="📊 Monitor"))
@admin_only
async def cmd_monitor(msg: types.Message, **kwargs):
    wait = await msg.reply("⏳ Generating dashboard…")
    names    = [p["name"] for p in _projects()]
    snapshot = mon_mod.full_snapshot(names)

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        path = tmp.name

    ok = mon_mod.generate_monitor_image(snapshot, path)
    await bot.delete_message(msg.chat.id, wait.message_id)

    if ok:
        caption = (
            f"<b>VPS Monitor</b>  {snapshot['timestamp']}\n"
            f"CPU <code>{snapshot['cpu']:.1f}%</code>  "
            f"MEM <code>{snapshot['mem']['percent']:.0f}%</code>  "
            f"DISK <code>{snapshot['disk']['percent']:.0f}%</code>"
        )
        await msg.reply_photo(InputFile(path), caption=caption)
    else:
        lines = [
            "<b>System Monitor</b>",
            f"CPU:  {snapshot['cpu']:.1f}%",
            f"MEM:  {snapshot['mem']['used_mb']:.0f}/{snapshot['mem']['total_mb']:.0f} MB",
            f"DISK: {snapshot['disk']['used_gb']:.1f}/{snapshot['disk']['total_gb']:.1f} GB",
            f"Load: {snapshot['load_avg'][0]:.2f} {snapshot['load_avg'][1]:.2f} {snapshot['load_avg'][2]:.2f}",
            "", "<b>Services:</b>",
        ]
        for n, sd in snapshot["services"].items():
            lines.append(f"  {n}: CPU {sd['cpu_percent']:.1f}%  MEM {sd['mem_mb']:.0f}MB")
        await msg.reply("\n".join(lines))

    try:
        os.unlink(path)
    except OSError:
        pass


# ─── /projects ────────────────────────────────────────────────────────────────

@dp.message_handler(commands=["projects"])
@admin_only
async def cmd_projects(msg: types.Message, **kwargs):
    await msg.reply("Select a project:", reply_markup=_projects_kb())


@dp.callback_query_handler(lambda c: c.data == "proj_list")
@admin_only_cb
async def cb_proj_list(call: types.CallbackQuery):
    await call.message.edit_text("Select a project:", reply_markup=_projects_kb())


@dp.callback_query_handler(lambda c: c.data.startswith("proj:"))
@admin_only_cb
async def cb_proj_detail(call: types.CallbackQuery):
    name    = call.data.split(":", 1)[1]
    config  = _cfg()
    project = cfg_mod.get_project(config, name)
    if not project:
        await call.answer("Project not found.", show_alert=True)
        return

    if svc_mod.unit_file_exists(name):
        st    = svc_mod.get_service_status(name)
        state = st["state"]
    else:
        state = "no-unit"

    await call.message.edit_text(
        f"<b>{name}</b>\n\n"
        f"Type:    <code>{project.get('type','?')}</code>\n"
        f"Port:    <code>{project.get('port','—')}</code>\n"
        f"Route:   <code>{project.get('route','—')}</code>\n"
        f"Status:  {_emoji(state)} <code>{state}</code>\n"
        f"Command: <code>{project.get('runcommand','')[:80]}</code>",
        reply_markup=_actions_kb(name),
    )


# ─── Service actions ──────────────────────────────────────────────────────────

async def _do_svc(call: types.CallbackQuery, action: str, name: str):
    fn = {"svc_start": svc_mod.start_service,
          "svc_stop":  svc_mod.stop_service,
          "svc_restart": svc_mod.restart_service}.get(action)
    if not fn:
        return

    if action == "svc_start" and not svc_mod.unit_file_exists(name):
        project = cfg_mod.get_project(_cfg(), name)
        if project:
            ok_w, msg_w = svc_mod.write_unit_file(project)
            if not ok_w:
                await call.answer(f"Unit error: {msg_w}", show_alert=True)
                return

    await call.answer("Working…")
    ok, msg = fn(name)
    state = svc_mod.get_service_status(name)["state"] \
            if svc_mod.unit_file_exists(name) else "no-unit"
    log_mod.log(f"bot {action} {name}: {msg}", "info" if ok else "error")
    await call.message.edit_text(
        f"{'✅' if ok else '❌'} <b>{name}</b>: {msg}\n\n"
        f"State: {_emoji(state)} <code>{state}</code>",
        reply_markup=_actions_kb(name),
    )


@dp.callback_query_handler(lambda c: c.data.startswith("svc_start:"))
@admin_only_cb
async def cb_start(call: types.CallbackQuery):
    await _do_svc(call, "svc_start", call.data.split(":", 1)[1])

@dp.callback_query_handler(lambda c: c.data.startswith("svc_stop:"))
@admin_only_cb
async def cb_stop(call: types.CallbackQuery):
    await _do_svc(call, "svc_stop", call.data.split(":", 1)[1])

@dp.callback_query_handler(lambda c: c.data.startswith("svc_restart:"))
@admin_only_cb
async def cb_restart(call: types.CallbackQuery):
    await _do_svc(call, "svc_restart", call.data.split(":", 1)[1])


# ─── Logs callback ────────────────────────────────────────────────────────────

@dp.callback_query_handler(lambda c: c.data.startswith("svc_logs:"))
@admin_only_cb
async def cb_logs(call: types.CallbackQuery):
    name = call.data.split(":", 1)[1]
    await call.answer()
    if not svc_mod.unit_file_exists(name):
        await call.message.reply(f"No unit file for <b>{name}</b>.")
        return
    st   = svc_mod.get_service_status(name)
    text = "\n".join((st["logs"] or "(no logs)").splitlines()[-40:])
    if len(text) > 3800:
        text = "…" + text[-3800:]
    await call.message.reply(
        f"<b>Logs: {name}</b>\n\n<pre>{text}</pre>",
        reply_markup=InlineKeyboardMarkup().add(
            InlineKeyboardButton("⬅ Back", callback_data=f"proj:{name}")
        ),
    )


# ─── Metrics PNG ──────────────────────────────────────────────────────────────

@dp.callback_query_handler(lambda c: c.data.startswith("svc_metrics:"))
@admin_only_cb
async def cb_metrics(call: types.CallbackQuery):
    name = call.data.split(":", 1)[1]
    await call.answer("Generating…")
    snap = mon_mod.full_snapshot([name])

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        path = tmp.name

    ok = mon_mod.generate_monitor_image(snap, path)
    sd = snap["services"].get(name, {})

    if ok:
        await call.message.reply_photo(
            InputFile(path),
            caption=(
                f"<b>Metrics: {name}</b>\n"
                f"CPU <code>{sd.get('cpu_percent',0):.1f}%</code>  "
                f"MEM <code>{sd.get('mem_mb',0):.1f} MB</code>  "
                f"PID <code>{sd.get('pid','—')}</code>"
            ),
        )
    else:
        await call.message.reply(
            f"<b>Metrics: {name}</b>\n"
            f"CPU <code>{sd.get('cpu_percent',0):.1f}%</code>\n"
            f"MEM <code>{sd.get('mem_mb',0):.1f} MB</code>\n"
            f"PID <code>{sd.get('pid','—')}</code>"
        )
    try:
        os.unlink(path)
    except OSError:
        pass


# ─── /logs ────────────────────────────────────────────────────────────────────

@dp.message_handler(commands=["logs"])
@dp.message_handler(Text(equals="📜 Logs"))
@admin_only
async def cmd_logs(msg: types.Message, **kwargs):
    arg = msg.get_args().strip()
    if not arg:
        await msg.reply("Select a service:", reply_markup=_projects_kb("logs_svc"))
        return
    await _send_logs(msg, arg)


@dp.callback_query_handler(lambda c: c.data.startswith("logs_svc:"))
@admin_only_cb
async def cb_logs_select(call: types.CallbackQuery):
    name = call.data.split(":", 1)[1]
    await call.answer()
    if not svc_mod.unit_file_exists(name):
        await call.message.reply(f"No unit file for <b>{name}</b>.")
        return
    st   = svc_mod.get_service_status(name)
    text = "\n".join((st["logs"] or "(no logs)").splitlines()[-40:])
    if len(text) > 3800:
        text = "…" + text[-3800:]
    await call.message.reply(f"<b>Logs: {name}</b>\n\n<pre>{text}</pre>")


async def _send_logs(msg: types.Message, name: str):
    if not svc_mod.unit_file_exists(name):
        await msg.reply(f"No unit file for <b>{name}</b>.")
        return
    st   = svc_mod.get_service_status(name)
    text = "\n".join((st["logs"] or "(no logs)").splitlines()[-40:])
    if len(text) > 3800:
        text = "…" + text[-3800:]
    await msg.reply(f"<b>Logs: {name}</b>\n\n<pre>{text}</pre>")


# ─── /ssl ─────────────────────────────────────────────────────────────────────

@dp.message_handler(commands=["ssl"])
@dp.message_handler(Text(equals="🔒 SSL"))
@admin_only
async def cmd_ssl(msg: types.Message, **kwargs):
    certs = ssl_mod.list_certificates()
    if not certs:
        await msg.reply("No Let's Encrypt certificates found.")
        return
    lines = ["<b>SSL Certificates</b>\n"]
    for c in certs:
        days = None
        for d in c.get("domains", []):
            days = ssl_mod.certificate_expiry_days(d)
            if days is not None:
                break
        if days is None:   em, ds = "🔒", "?"
        elif days < 0:     em, ds = "🔴", f"EXPIRED ({abs(days)}d ago)"
        elif days < 14:    em, ds = "🟡", f"{days}d ⚠️"
        else:              em, ds = "🟢", f"{days}d"
        lines.append(
            f"{em} <b>{c.get('name','?')}</b>\n"
            f"   <code>{', '.join(c.get('domains',[]))}</code>\n"
            f"   Expires: {ds}"
        )
    await msg.reply("\n\n".join(lines))


# ─── /renew ───────────────────────────────────────────────────────────────────

@dp.message_handler(commands=["renew"])
@dp.message_handler(Text(equals="🔄 Renew SSL"))
@admin_only
async def cmd_renew(msg: types.Message, **kwargs):
    wait = await msg.reply("⏳ Running certbot renew…")
    ok, output = ssl_mod.renew_certificates(dry_run=False)
    await bot.delete_message(msg.chat.id, wait.message_id)
    truncated = "\n".join(output.splitlines()[-30:])
    if len(truncated) > 3500:
        truncated = "…" + truncated[-3500:]
    status = "✅ Renewal complete" if ok else "❌ Renewal had errors"
    await msg.reply(f"{status}\n\n<pre>{truncated}</pre>")


# ─── Alert poller ─────────────────────────────────────────────────────────────

async def _alert_poller():
    await asyncio.sleep(15)
    while True:
        try:
            config   = cfg_mod.load_config()
            projects = config.get("projects", [])
            now      = time.time()
            for p in projects:
                name = p["name"]
                if not svc_mod.unit_file_exists(name):
                    continue
                st    = svc_mod.get_service_status(name)
                state = st["state"]
                if state == "failed":
                    if now - _alerted.get(name, 0) < 300:
                        continue
                    _alerted[name] = now
                    last = st["logs"].splitlines()[-1] if st["logs"] else "(no logs)"
                    text = (
                        f"🔴 <b>ALERT: {name} crashed</b>\n\n"
                        f"State: <code>failed</code>\n"
                        f"Last log:\n<pre>{last[:500]}</pre>"
                    )
                    kb = InlineKeyboardMarkup().add(
                        InlineKeyboardButton("🔄 Restart", callback_data=f"svc_restart:{name}"),
                        InlineKeyboardButton("📜 Logs",    callback_data=f"svc_logs:{name}"),
                    )
                    for aid in ADMIN_IDS:
                        try:
                            await bot.send_message(aid, text, reply_markup=kb,
                                                   parse_mode=ParseMode.HTML)
                        except (BotBlocked, ChatNotFound):
                            pass
                        except Exception as e:
                            logger.warning(f"Alert send failed: {e}")
                else:
                    _alerted.pop(name, None)
        except Exception as e:
            logger.error(f"Alert poller error: {e}")
        await asyncio.sleep(60)


# ─── Startup / shutdown ───────────────────────────────────────────────────────

async def on_startup(dp):
    asyncio.ensure_future(_alert_poller())
    projects = _projects()
    n_ok = sum(
        1 for p in projects
        if svc_mod.unit_file_exists(p["name"]) and
           svc_mod.get_service_status(p["name"])["state"] == "active"
    )
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(
                aid,
                f"✅ <b>VPS Manager Bot started</b>\n"
                f"Services: <b>{n_ok}/{len(projects)}</b> active\n"
                f"Uptime: <code>{mon_mod.uptime_str()}</code>",
                reply_markup=_main_kb(),
            )
        except Exception:
            pass


async def on_shutdown(dp):
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, "⚠️ <b>VPS Manager Bot stopped.</b>")
        except Exception:
            pass
    await bot.close()


if __name__ == "__main__":
    log_mod.log("Bot starting", "info")
    executor.start_polling(
        dp,
        on_startup=on_startup,
        on_shutdown=on_shutdown,
        skip_updates=True,
    )