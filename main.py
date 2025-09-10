import os
import logging
from datetime import datetime, time as dtime
import pytz
from telegram.ext import Updater, CommandHandler

from picks import build_daily_message

# --------- Config via variables d'environnement ----------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")            # ex: -1002923920062
TZNAME = os.getenv("TIMEZONE", "Australia/Sydney")
TZ = pytz.timezone(TZNAME)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("bot")

LAST_SENT = ".last_sent_date.txt"


def _already_sent_today():
    try:
        with open(LAST_SENT, "r") as f:
            return f.read().strip() == datetime.now(TZ).date().isoformat()
    except FileNotFoundError:
        return False


def _mark_sent_today():
    with open(LAST_SENT, "w") as f:
        f.write(datetime.now(TZ).date().isoformat())


# -------------------- Commandes --------------------
def cmd_start(update, context):
    update.message.reply_text(
        "Bot en ligne ✅\n"
        "• /sendnow pour publier tout de suite."
    )


def cmd_sendnow(update, context):
    msg = build_daily_message()
    context.bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
    _mark_sent_today()
    update.message.reply_text("Envoyé 👌")


# -------------------- Tâches --------------------
def job_daily(context):
    msg = build_daily_message()
    context.bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
    _mark_sent_today()


def catch_up_if_needed(bot):
    """Si on démarre après 18h (heure Sydney) et rien n'a été envoyé, on rattrape."""
    now = datetime.now(TZ)
    target = now.replace(hour=18, minute=0, second=0, microsecond=0)
    if now >= target and not _already_sent_today():
        log.info("Rattrapage après 18h")
        msg = build_daily_message()
        bot.send_message(chat_id=CHANNEL_ID, text=msg, parse_mode="Markdown")
        _mark_sent_today()


def main():
    if not TOKEN or not CHANNEL_ID:
        raise SystemExit("❌ Manque TELEGRAM_BOT_TOKEN ou CHANNEL_ID (Variables Render).")

    updater = Updater(TOKEN, use_context=True)
    dp = updater.dispatcher

    # Commandes
    dp.add_handler(CommandHandler("start", cmd_start))
    dp.add_handler(CommandHandler("sendnow", cmd_sendnow))

    # Job quotidien 18:00 (Sydney) + tolérance si le process a dormi
    updater.job_queue.run_daily(
        job_daily,
        time=dtime(hour=18, minute=0, tzinfo=TZ),
        name="daily18",
        job_kwargs={"misfire_grace_time": 3600, "coalesce": True},
    )

    # Démarrage
    updater.start_polling()
    log.info("Bot démarré | TZ=%s | Local=%s", TZNAME, datetime.now(TZ).strftime("%Y-%m-%d %H:%M"))

    # Rattrapage si besoin
    catch_up_if_needed(updater.bot)

    updater.idle()


if __name__ == "__main__":
    main()
