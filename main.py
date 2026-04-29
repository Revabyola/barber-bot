import logging
import os
import threading

from flask import Flask
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
)

import db
from reminders import reschedule_all
from handlers.client import (
    cmd_start, show_services_list, show_my_appointments,
    booking_conv, appt_callbacks,
)
from handlers.barber import (
    cmd_admin, cmd_cancel,
    set_hours_conv, service_conv,
    barber_callbacks,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]

flask_app = Flask(__name__)


@flask_app.route("/health")
def health():
    return "OK", 200


def _run_flask():
    port = int(os.environ.get("PORT", 10000))
    flask_app.run(host="0.0.0.0", port=port)


async def _post_init(application: Application):
    await reschedule_all(application)


def main():
    db.init_db()
    logger.info("Database initialized")

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(_post_init)
        .build()
    )

    # ConversationHandlers must be registered before generic handlers
    app.add_handler(booking_conv)
    app.add_handler(set_hours_conv)
    app.add_handler(service_conv)

    # Commands
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("admin", cmd_admin))
    app.add_handler(CommandHandler("cancel", cmd_cancel))

    # Reply keyboard buttons
    app.add_handler(MessageHandler(filters.Regex("^💈 Услуги и цены$"), show_services_list))
    app.add_handler(MessageHandler(filters.Regex("^📋 Мои записи$"), show_my_appointments))

    # Inline callback handlers — barber first (more specific patterns)
    for handler in barber_callbacks:
        app.add_handler(handler)

    # Inline callback handlers — client
    for handler in appt_callbacks:
        app.add_handler(handler)

    threading.Thread(target=_run_flask, daemon=True).start()
    logger.info("Bot started")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
