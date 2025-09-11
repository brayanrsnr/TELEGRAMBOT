import os
import logging
import threading
from datetime import datetime, time as dtime

import pytz
from flask import Flask, jsonify
from telegram.ext import Updater, CommandHandler

from picks import build_daily_message, build_status

# ------------- Config -------------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")         # ex: -1002923920062
TZNAME = os.getenv("TIMEZONE", "Australia/Sydney")
TZ = pytz.timezone(TZNAME)
PORT = int(os.getenv("PORT", "10000"))       # Render fournit PORT

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("bot")

LAST_SENT = ".last_sent_date.txt"

# ------------- Flask (Web Service) -------------
app = Flask(__name__)

@app.get("/")
def root():
    return "OK", 200

@app.get("/health")
def health():
    return jsonify(status="ok", tz=TZNAME, now=datetime.now(TZ).isoformat())

def run_web():
    # serveur HTTP non bloquant dans un thread
    app.run(host="0.0.0.0", port=PORT, threaded=True)

# ------------- Utilitaires -------------
def _already_sent_today():
    try:
        with open(LAST_SENT, "r") as f:
            return f.read().strip() == datetime.now(TZ).date().isoformat()
    except FileNotFoundError:
        return False

def _mark_sent_today():
    with open(LAST_SENT, "w") as f:
        f.write(datetime.now(TZ).date().isoformat())

# ------------- Commandes -------------
def cmd_start(update, context):
    update.message.reply_text("Bot en ligne ✅\n• /sendnow pour publier tout de suite.")

def cmd_sendnow(update, context):
    msg = build_daily_message()
    context.bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
    _mark_sent_today()
    update.message.reply_text("Envoyé 👌")

# ------------- Jobs -------------
def job_daily(context):
msg = build_daily_message()
    context.bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
    _mark_sent_today()

def catch_up_if_needed(bot):
    now = datetime.now(TZ)
    target = now.replace(hour=18, minute=0, second=0, microsecond=0)
    if now >= target and not _already_sent_today():
        log.info("Rattrapage après 18h")
        msg = build_daily_message()
        bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
        _mark_sent_today()

# ------------- Main -------------
def main():
    if not TOKEN or not CHANNEL_ID:
        raise SystemExit("❌ Manque TELEGRAM_BOT_TOKEN ou CHANNEL_ID (Variables Render).")

    # 1) Démarrer le serveur web dans un thread (pour Render Web Service)
    threading.Thread(target=run_web, daemon=True).start()
    log.info("Web server started on port %s", PORT)

    # 2) Démarrer le bot
    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    dp.add_handler(CommandHandler("start", cmd_start))
    dp.add_handler(CommandHandler("sendnow", cmd_sendnow))

    updater.job_queue.run_daily(
        job_daily,
        time=dtime(hour=18, minute=0, tzinfo=TZ),
        name="daily18",
        job_kwargs={"misfire_grace_time": 3600, "coalesce": True},
    )

    updater.start_polling()
    log.info("Bot démarré | TZ=%s | Local=%s", TZNAME, datetime.now(TZ).strftime("%Y-%m-%d %H:%M"))
    catch_up_if_needed(updater.bot)
    updater.idle()

if __name__ == "__main__":
    main()
