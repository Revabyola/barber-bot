import logging
import os
from datetime import datetime, date, time as dtime
import pytz
from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler,
    MessageHandler, CommandHandler, filters,
)
import db
import keyboards as kb

logger = logging.getLogger(__name__)
TZ = pytz.timezone("Europe/Moscow")
BARBER_ID = int(os.environ.get("BARBER_TELEGRAM_ID", "0"))

# ConversationHandler states for booking flow
SERVICE_SELECT, DATE_SELECT, TIME_SELECT, BOOKING_CONFIRM = range(4)


# ─── /start ─────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "друг"
    await update.message.reply_text(
        f"Привет, {name}! 👋\n\nДобро пожаловать в барбершоп.\nВыберите действие:",
        reply_markup=kb.client_main_menu(),
    )


# ─── Static menu buttons ─────────────────────────────────────────────────────

async def show_services_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    services = db.get_services()
    if not services:
        await update.message.reply_text("Услуги пока не добавлены. Загляните позже.")
        return
    text = "💈 *Услуги и цены:*\n\n" + "".join(
        f"• *{s['name']}* — {s['price']} руб. ({s['duration_minutes']} мин)\n"
        for s in services
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def show_my_appointments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    appts = db.get_client_appointments(update.effective_user.id)
    if not appts:
        await update.message.reply_text("У вас нет предстоящих записей.")
        return
    await update.message.reply_text("Ваши предстоящие записи:", reply_markup=kb.my_appointments_kb(appts))


# ─── My appointments callbacks ───────────────────────────────────────────────

async def appt_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "c_my_appts":
        appts = db.get_client_appointments(update.effective_user.id)
        if not appts:
            await query.edit_message_text("У вас нет предстоящих записей.")
        else:
            await query.edit_message_text("Ваши предстоящие записи:", reply_markup=kb.my_appointments_kb(appts))
        return

    appt_id = int(query.data.split("_")[1])
    appt = db.get_appointment(appt_id)
    if not appt or appt["client_id"] != update.effective_user.id:
        await query.edit_message_text("Запись не найдена.")
        return

    status_map = {
        "pending": "⏳ Ожидает подтверждения",
        "confirmed": "✅ Подтверждена",
        "cancelled": "❌ Отменена",
    }
    dt_str = kb.fmt_dt(appt["appointment_dt"])
    text = (
        f"📋 *Детали записи:*\n\n"
        f"✂️ Услуга: {appt['service_name']}\n"
        f"📅 Дата и время: {dt_str}\n"
        f"Статус: {status_map.get(appt['status'], appt['status'])}"
    )
    await query.edit_message_text(text, reply_markup=kb.appt_detail_kb(appt_id, appt["status"]), parse_mode="Markdown")


async def cancel_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    appt_id = int(query.data.split("_")[1])
    await query.edit_message_text(
        "Вы уверены, что хотите отменить запись?",
        reply_markup=kb.cancel_confirm_kb(appt_id),
    )


async def cancel_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    appt_id = int(query.data.split("_")[1])
    appt = db.get_appointment(appt_id)

    if not appt or appt["client_id"] != update.effective_user.id:
        await query.edit_message_text("Запись не найдена.")
        return

    db.update_appointment_status(appt_id, "cancelled")
    await query.edit_message_text("✅ Запись отменена.")

    if BARBER_ID and appt["status"] == "confirmed":
        dt_str = kb.fmt_dt(appt["appointment_dt"])
        user = update.effective_user
        await context.bot.send_message(
            chat_id=BARBER_ID,
            text=f"❌ Клиент {user.full_name} отменил запись на {dt_str} ({appt['service_name']}).",
        )


# ─── Booking ConversationHandler ─────────────────────────────────────────────

async def book_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    services = db.get_services()
    if not services:
        await update.message.reply_text("Услуги пока не добавлены. Попробуйте позже.")
        return ConversationHandler.END
    await update.message.reply_text("Выберите услугу:", reply_markup=kb.services_kb(services))
    return SERVICE_SELECT


async def service_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "c_back_main":
        await query.edit_message_text("Главное меню.", reply_markup=None)
        return ConversationHandler.END

    if query.data == "noop":
        return SERVICE_SELECT

    service_id = int(query.data.split("_")[1])
    service = db.get_service(service_id)
    if not service:
        await query.edit_message_text("Услуга не найдена.")
        return ConversationHandler.END

    context.user_data["service"] = dict(service)
    hours_map = {h["day_of_week"]: h for h in db.get_working_hours()}
    await query.edit_message_text(
        f"Услуга: *{service['name']}*\n\nВыберите дату:",
        reply_markup=kb.dates_kb(hours_map),
        parse_mode="Markdown",
    )
    return DATE_SELECT


async def date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "c_back_service":
        services = db.get_services()
        await query.edit_message_text("Выберите услугу:", reply_markup=kb.services_kb(services))
        return SERVICE_SELECT

    if query.data == "noop":
        return DATE_SELECT

    selected_date = date.fromisoformat(query.data.split("_", 1)[1])
    context.user_data["date"] = selected_date

    service = context.user_data["service"]
    booked = db.get_booked_slots(selected_date)
    blocked = db.get_blocked_slots_for_date(selected_date)

    from keyboards import DAYS_RU_FULL, MONTHS_RU_GEN
    date_label = f"{DAYS_RU_FULL[selected_date.weekday()]}, {selected_date.day} {MONTHS_RU_GEN[selected_date.month - 1]}"

    await query.edit_message_text(
        f"Услуга: *{service['name']}*\nДата: *{date_label}*\n\nВыберите время:",
        reply_markup=kb.times_kb(selected_date, service["duration_minutes"], booked, blocked),
        parse_mode="Markdown",
    )
    return TIME_SELECT


async def time_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "c_back_date":
        service = context.user_data["service"]
        hours_map = {h["day_of_week"]: h for h in db.get_working_hours()}
        await query.edit_message_text(
            f"Услуга: *{service['name']}*\n\nВыберите дату:",
            reply_markup=kb.dates_kb(hours_map),
            parse_mode="Markdown",
        )
        return DATE_SELECT

    if query.data == "noop":
        return TIME_SELECT

    time_str = query.data.split("_", 1)[1]
    hour, minute = map(int, time_str.split(":"))
    selected_date = context.user_data["date"]
    appointment_dt = TZ.localize(datetime.combine(selected_date, dtime(hour, minute)))
    context.user_data["appointment_dt"] = appointment_dt

    service = context.user_data["service"]
    from keyboards import DAYS_RU_FULL, MONTHS_RU_GEN
    date_label = f"{DAYS_RU_FULL[selected_date.weekday()]}, {selected_date.day} {MONTHS_RU_GEN[selected_date.month - 1]}"

    text = (
        f"📋 *Подтверждение записи:*\n\n"
        f"✂️ Услуга: *{service['name']}*\n"
        f"💰 Цена: *{service['price']} руб.*\n"
        f"⏱ Длительность: *{service['duration_minutes']} мин*\n"
        f"📅 Дата: *{date_label}*\n"
        f"🕐 Время: *{time_str}*"
    )
    await query.edit_message_text(text, reply_markup=kb.confirm_booking_kb(), parse_mode="Markdown")
    return BOOKING_CONFIRM


async def booking_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "bk_no":
        await query.edit_message_text("Запись отменена.")
        return ConversationHandler.END

    user = update.effective_user
    service = context.user_data["service"]
    appointment_dt = context.user_data["appointment_dt"]

    appt_utc_naive = appointment_dt.astimezone(pytz.utc).replace(tzinfo=None)
    appt_id = db.create_appointment(
        client_id=user.id,
        client_name=user.full_name,
        client_username=user.username,
        service_id=service["id"],
        service_name=service["name"],
        appointment_dt=appt_utc_naive,
        duration=service["duration_minutes"],
    )

    await query.edit_message_text(
        "✅ Ваша заявка отправлена!\n\n"
        "Ожидайте подтверждения от барбера. "
        "Мы уведомим вас, как только запись будет подтверждена."
    )

    if BARBER_ID:
        dt_str = appointment_dt.strftime("%d.%m.%Y в %H:%M")
        client_info = user.full_name + (f" (@{user.username})" if user.username else "")
        await context.bot.send_message(
            chat_id=BARBER_ID,
            text=(
                f"🔔 *Новая заявка!*\n\n"
                f"👤 Клиент: {client_info}\n"
                f"✂️ Услуга: {service['name']}\n"
                f"📅 Дата и время: {dt_str}\n\n"
                f"Откройте /admin для подтверждения."
            ),
            parse_mode="Markdown",
        )

    context.user_data.clear()
    return ConversationHandler.END


# ─── Build handlers ──────────────────────────────────────────────────────────

booking_conv = ConversationHandler(
    entry_points=[MessageHandler(filters.Regex("^✂️ Записаться$"), book_start)],
    states={
        SERVICE_SELECT: [CallbackQueryHandler(service_chosen, pattern="^(srv_|c_back_main|noop)")],
        DATE_SELECT: [CallbackQueryHandler(date_chosen, pattern="^(date_|c_back_service|noop)")],
        TIME_SELECT: [CallbackQueryHandler(time_chosen, pattern="^(time_|c_back_date|noop)")],
        BOOKING_CONFIRM: [CallbackQueryHandler(booking_confirm, pattern="^bk_")],
    },
    fallbacks=[CommandHandler("start", cmd_start)],
    per_user=True,
    per_chat=True,
)

# Standalone callback handlers (outside booking flow)
appt_callbacks = [
    CallbackQueryHandler(appt_detail, pattern="^myappt_"),
    CallbackQueryHandler(appt_detail, pattern="^c_my_appts$"),
    CallbackQueryHandler(cancel_prompt, pattern="^cancel_\\d+$"),
    CallbackQueryHandler(cancel_yes, pattern="^cancelyes_"),
]
