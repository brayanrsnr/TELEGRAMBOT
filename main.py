import os, logging
from datetime import datetime, time as dtime
import pytz
from telegram.ext import Updater, CommandHandler
from picks import build_daily_message

# ------- Config -------
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHANNEL_ID = os.getenv("CHANNEL_ID")           # ex: -100292
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

