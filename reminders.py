import logging
import os
from datetime import datetime, timedelta
import pytz
import db

logger = logging.getLogger(__name__)
TZ = pytz.timezone("Europe/Moscow")
BARBER_ID = int(os.environ.get("BARBER_TELEGRAM_ID", "0"))


def _localize(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return pytz.utc.localize(dt).astimezone(TZ)
    return dt.astimezone(TZ)


async def _send_reminder(context):
    appt_id, reminder_type = context.job.data
    appt = db.get_appointment(appt_id)
    if not appt or appt["status"] != "confirmed":
        return

    dt_str = _localize(appt["appointment_dt"]).strftime("%d.%m.%Y в %H:%M")
    label = "за 1 день" if reminder_type == "1day" else "за 2 часа"

    client_text = (
        f"⏰ *Напоминание* ({label})\n\n"
        f"✂️ Услуга: {appt['service_name']}\n"
        f"📅 Дата и время: {dt_str}\n\n"
        f"Ждём вас!"
    )
    barber_text = (
        f"⏰ *Напоминание* ({label})\n\n"
        f"👤 Клиент: {appt['client_name'] or 'Неизвестный'}"
        + (f" (@{appt['client_username']})" if appt["client_username"] else "") + "\n"
        f"✂️ Услуга: {appt['service_name']}\n"
        f"📅 Дата и время: {dt_str}"
    )

    try:
        await context.bot.send_message(chat_id=appt["client_id"], text=client_text, parse_mode="Markdown")
    except Exception as e:
        logger.error("Reminder to client failed: %s", e)

    try:
        if BARBER_ID:
            await context.bot.send_message(chat_id=BARBER_ID, text=barber_text, parse_mode="Markdown")
    except Exception as e:
        logger.error("Reminder to barber failed: %s", e)

    db.mark_reminder_sent(appt_id, reminder_type)


def schedule_reminders(app, appt_id: int, appointment_dt: datetime):
    now = datetime.now(TZ)
    appt_local = _localize(appointment_dt)
    appt = db.get_appointment(appt_id)

    fire_1day = appt_local - timedelta(days=1)
    fire_2hour = appt_local - timedelta(hours=2)

    if fire_1day > now and not appt.get("reminder_1day_sent"):
        app.job_queue.run_once(
            _send_reminder,
            when=(fire_1day - now).total_seconds(),
            data=(appt_id, "1day"),
            name=f"rem1d_{appt_id}",
        )

    if fire_2hour > now and not appt.get("reminder_2hour_sent"):
        app.job_queue.run_once(
            _send_reminder,
            when=(fire_2hour - now).total_seconds(),
            data=(appt_id, "2hour"),
            name=f"rem2h_{appt_id}",
        )


async def reschedule_all(app):
    confirmed = db.get_upcoming_confirmed()
    for appt in confirmed:
        schedule_reminders(app, appt["id"], appt["appointment_dt"])
    logger.info("Re-scheduled reminders for %d appointments", len(confirmed))
