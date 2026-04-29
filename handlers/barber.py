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
from reminders import schedule_reminders

logger = logging.getLogger(__name__)
TZ = pytz.timezone("Europe/Moscow")
BARBER_ID = int(os.environ.get("BARBER_TELEGRAM_ID", "0"))

# States for add/edit service conversation
SVC_NAME, SVC_PRICE, SVC_DURATION = range(10, 13)
# States for set working hours conversation
HOURS_START, HOURS_END = range(13, 15)


def _is_barber(update: Update) -> bool:
    return update.effective_user.id == BARBER_ID


# ─── /admin entry ────────────────────────────────────────────────────────────

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_barber(update):
        await update.message.reply_text("У вас нет доступа к этой команде.")
        return
    await update.message.reply_text("🔧 *Панель барбера*", reply_markup=kb.barber_main_kb(), parse_mode="Markdown")


async def cb_barber_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    await query.edit_message_text("🔧 *Панель барбера*", reply_markup=kb.barber_main_kb(), parse_mode="Markdown")


# ─── Requests ────────────────────────────────────────────────────────────────

async def cb_requests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    requests = db.get_pending_appointments()
    await query.edit_message_text("📋 *Новые заявки:*", reply_markup=kb.barber_requests_kb(requests), parse_mode="Markdown")


async def cb_request_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    appt_id = int(query.data.split("_")[1])
    appt = db.get_appointment(appt_id)
    if not appt:
        await query.edit_message_text("Заявка не найдена.")
        return
    dt_str = kb.fmt_dt(appt["appointment_dt"])
    client_info = appt["client_name"] or "Клиент"
    if appt["client_username"]:
        client_info += f" (@{appt['client_username']})"
    text = (
        f"📋 *Заявка #{appt_id}*\n\n"
        f"👤 Клиент: {client_info}\n"
        f"✂️ Услуга: {appt['service_name']}\n"
        f"📅 Дата и время: {dt_str}"
    )
    await query.edit_message_text(text, reply_markup=kb.request_actions_kb(appt_id), parse_mode="Markdown")


async def cb_approve(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    appt_id = int(query.data.split("_")[1])
    appt = db.get_appointment(appt_id)
    if not appt or appt["status"] != "pending":
        await query.edit_message_text("Заявка уже обработана.")
        return
    db.update_appointment_status(appt_id, "confirmed")
    schedule_reminders(context.application, appt_id, appt["appointment_dt"])

    dt_str = kb.fmt_dt(appt["appointment_dt"])
    await query.edit_message_text(f"✅ Запись подтверждена: {appt['client_name']} | {appt['service_name']} | {dt_str}")

    try:
        await context.bot.send_message(
            chat_id=appt["client_id"],
            text=(
                f"✅ *Ваша запись подтверждена!*\n\n"
                f"✂️ Услуга: {appt['service_name']}\n"
                f"📅 Дата и время: {dt_str}\n\n"
                f"Ждём вас!"
            ),
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error("Failed to notify client: %s", e)


async def cb_decline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    appt_id = int(query.data.split("_")[1])
    appt = db.get_appointment(appt_id)
    if not appt or appt["status"] != "pending":
        await query.edit_message_text("Заявка уже обработана.")
        return
    db.update_appointment_status(appt_id, "cancelled")

    dt_str = kb.fmt_dt(appt["appointment_dt"])
    await query.edit_message_text(f"❌ Заявка отклонена: {appt['client_name']} | {appt['service_name']} | {dt_str}")

    try:
        await context.bot.send_message(
            chat_id=appt["client_id"],
            text=(
                f"❌ К сожалению, барбер не смог подтвердить вашу запись.\n\n"
                f"✂️ Услуга: {appt['service_name']}\n"
                f"📅 Дата и время: {dt_str}\n\n"
                f"Попробуйте выбрать другое время."
            ),
        )
    except Exception as e:
        logger.error("Failed to notify client: %s", e)


# ─── Schedule ─────────────────────────────────────────────────────────────────

async def cb_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    await query.edit_message_text("📅 *Расписание*", reply_markup=kb.barber_schedule_kb(), parse_mode="Markdown")


async def cb_day_appointments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    await query.edit_message_text("Выберите день:", reply_markup=kb.select_day_kb("dayappt"))


async def cb_day_appt_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    target_date = date.fromisoformat(query.data.split("_", 1)[1])
    appts = db.get_appointments_for_day(target_date)

    from keyboards import DAYS_RU_FULL, MONTHS_RU_GEN
    date_label = f"{DAYS_RU_FULL[target_date.weekday()]}, {target_date.day} {MONTHS_RU_GEN[target_date.month - 1]}"

    if not appts:
        text = f"📋 *{date_label}*\n\nЗаписей нет."
    else:
        lines = [f"📋 *{date_label}*\n"]
        for a in appts:
            dt_str = kb.fmt_dt(a["appointment_dt"])
            client_info = a["client_name"] or "Клиент"
            lines.append(f"• {dt_str.split(' в ')[1]} — {client_info} ({a['service_name']})")
        text = "\n".join(lines)

    await query.edit_message_text(
        text,
        reply_markup=kb.barber_schedule_kb(),
        parse_mode="Markdown",
    )


# ─── Working hours conversation ───────────────────────────────────────────────

async def cb_hours(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    hours = db.get_working_hours()
    await query.edit_message_text("🕐 *Рабочие часы:*\nВыберите день для редактирования:", reply_markup=kb.working_hours_kb(hours), parse_mode="Markdown")


async def cb_edit_day(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    dow = int(query.data.split("_")[1])
    context.user_data["edit_dow"] = dow
    day_name = kb.DAYS_RU_FULL[dow]
    await query.edit_message_text(
        f"*{day_name}* — рабочий день или выходной?",
        reply_markup=kb.day_work_choice_kb(dow),
        parse_mode="Markdown",
    )


async def cb_day_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    dow = int(query.data.split("_")[1])
    db.set_day_hours(dow, False)
    hours = db.get_working_hours()
    await query.edit_message_text("✅ Сохранено как выходной.\n\n🕐 *Рабочие часы:*", reply_markup=kb.working_hours_kb(hours), parse_mode="Markdown")


async def cb_day_work(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    dow = int(query.data.split("_")[1])
    context.user_data["edit_dow"] = dow
    await query.edit_message_text(
        f"Введите время *начала* работы (например: `10:00`):",
        parse_mode="Markdown",
    )
    return HOURS_START


async def hours_get_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_barber(update):
        return ConversationHandler.END
    text = update.message.text.strip()
    try:
        h, m = map(int, text.split(":"))
        dtime(h, m)
    except (ValueError, TypeError):
        await update.message.reply_text("Неверный формат. Введите время в формате ЧЧ:ММ, например `10:00`:", parse_mode="Markdown")
        return HOURS_START
    context.user_data["hours_start"] = text
    await update.message.reply_text(f"Введите время *окончания* работы (например: `20:00`):", parse_mode="Markdown")
    return HOURS_END


async def hours_get_end(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_barber(update):
        return ConversationHandler.END
    text = update.message.text.strip()
    try:
        h, m = map(int, text.split(":"))
        dtime(h, m)
    except (ValueError, TypeError):
        await update.message.reply_text("Неверный формат. Введите время в формате ЧЧ:ММ, например `20:00`:", parse_mode="Markdown")
        return HOURS_END

    dow = context.user_data["edit_dow"]
    start = context.user_data["hours_start"]
    db.set_day_hours(dow, True, start, text)
    hours = db.get_working_hours()
    await update.message.reply_text(
        f"✅ Сохранено: {kb.DAYS_RU_FULL[dow]} {start}–{text}\n\n🕐 *Рабочие часы:*",
        reply_markup=kb.working_hours_kb(hours),
        parse_mode="Markdown",
    )
    context.user_data.pop("edit_dow", None)
    context.user_data.pop("hours_start", None)
    return ConversationHandler.END


# ─── Services conversation ────────────────────────────────────────────────────

async def cb_services(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    services = db.get_services(active_only=False)
    await query.edit_message_text("✂️ *Услуги:*", reply_markup=kb.barber_services_kb(services), parse_mode="Markdown")


async def cb_svc_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    svc_id = int(query.data.split("_")[1])
    active = db.toggle_service_active(svc_id)
    services = db.get_services(active_only=False)
    status = "показана" if active else "скрыта"
    await query.edit_message_text(f"✅ Услуга {status}.\n\n✂️ *Услуги:*", reply_markup=kb.barber_services_kb(services), parse_mode="Markdown")


async def cb_svc_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    context.user_data.pop("edit_svc_id", None)
    await query.edit_message_text("Введите *название* услуги:", parse_mode="Markdown")
    return SVC_NAME


async def cb_svc_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    svc_id = int(query.data.split("_")[1])
    svc = db.get_service(svc_id)
    if not svc:
        await query.edit_message_text("Услуга не найдена.")
        return ConversationHandler.END
    context.user_data["edit_svc_id"] = svc_id
    await query.edit_message_text(
        f"Редактирование: *{svc['name']}*\n\nВведите новое *название* (или отправьте `-` чтобы оставить прежнее):",
        parse_mode="Markdown",
    )
    context.user_data["old_svc"] = dict(svc)
    return SVC_NAME


async def svc_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_barber(update):
        return ConversationHandler.END
    name = update.message.text.strip()
    old = context.user_data.get("old_svc")
    if name == "-" and old:
        name = old["name"]
    context.user_data["svc_name"] = name
    await update.message.reply_text(f"Введите *цену* в рублях (целое число):", parse_mode="Markdown")
    return SVC_PRICE


async def svc_get_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_barber(update):
        return ConversationHandler.END
    text = update.message.text.strip()
    old = context.user_data.get("old_svc")
    if text == "-" and old:
        context.user_data["svc_price"] = old["price"]
        await update.message.reply_text(f"Введите *длительность* в минутах (например: `30` или `60`):", parse_mode="Markdown")
        return SVC_DURATION
    try:
        price = int(text)
        if price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Введите целое положительное число:")
        return SVC_PRICE
    context.user_data["svc_price"] = price
    await update.message.reply_text(f"Введите *длительность* в минутах (например: `30` или `60`):", parse_mode="Markdown")
    return SVC_DURATION


async def svc_get_duration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_barber(update):
        return ConversationHandler.END
    text = update.message.text.strip()
    old = context.user_data.get("old_svc")
    if text == "-" and old:
        duration = old["duration_minutes"]
    else:
        try:
            duration = int(text)
            if duration <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Введите целое положительное число минут:")
            return SVC_DURATION

    name = context.user_data["svc_name"]
    price = context.user_data["svc_price"]
    edit_id = context.user_data.get("edit_svc_id")

    if edit_id:
        db.update_service(edit_id, name, price, duration)
        msg = f"✅ Услуга обновлена: *{name}* — {price} руб. ({duration} мин)"
    else:
        db.add_service(name, price, duration)
        msg = f"✅ Услуга добавлена: *{name}* — {price} руб. ({duration} мин)"

    services = db.get_services(active_only=False)
    await update.message.reply_text(msg + "\n\n✂️ *Услуги:*", reply_markup=kb.barber_services_kb(services), parse_mode="Markdown")

    for key in ("svc_name", "svc_price", "edit_svc_id", "old_svc"):
        context.user_data.pop(key, None)
    return ConversationHandler.END


# ─── Block slots ──────────────────────────────────────────────────────────────

async def cb_block(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    await query.edit_message_text("🔒 Выберите день для блокировки:", reply_markup=kb.select_day_kb("blkdate"))


async def cb_block_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    target_date = date.fromisoformat(query.data.split("_", 1)[1])
    context.user_data["block_date"] = target_date

    booked = db.get_booked_slots(target_date)
    blocked = db.get_blocked_slots_for_date(target_date)

    from keyboards import DAYS_RU_FULL, MONTHS_RU_GEN
    date_label = f"{DAYS_RU_FULL[target_date.weekday()]}, {target_date.day} {MONTHS_RU_GEN[target_date.month - 1]}"

    await query.edit_message_text(
        f"🔒 *{date_label}*\n🔵 — занято клиентом  🔴 — заблокировано\n\nНажмите на слот для блокировки/разблокировки:",
        reply_markup=kb.block_times_kb(target_date, booked, blocked),
        parse_mode="Markdown",
    )


async def cb_block_slot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if not _is_barber(update):
        return
    time_str = query.data.split("_", 1)[1]
    target_date = context.user_data.get("block_date")
    if not target_date:
        await query.edit_message_text("Выберите день заново.", reply_markup=kb.select_day_kb("blkdate"))
        return

    hour, minute = map(int, time_str.split(":"))
    slot_dt = datetime.combine(target_date, dtime(hour, minute))
    blocked = db.toggle_blocked_slot(slot_dt)

    booked = db.get_booked_slots(target_date)
    blocked_list = db.get_blocked_slots_for_date(target_date)

    from keyboards import DAYS_RU_FULL, MONTHS_RU_GEN
    date_label = f"{DAYS_RU_FULL[target_date.weekday()]}, {target_date.day} {MONTHS_RU_GEN[target_date.month - 1]}"
    action = "заблокировано" if blocked else "разблокировано"

    await query.edit_message_text(
        f"✅ {time_str} {action}.\n\n🔒 *{date_label}*\n🔵 — занято клиентом  🔴 — заблокировано:",
        reply_markup=kb.block_times_kb(target_date, booked, blocked_list),
        parse_mode="Markdown",
    )


# ─── /cancel fallback ─────────────────────────────────────────────────────────

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("Действие отменено.")
    return ConversationHandler.END


# ─── Build conversation handlers ─────────────────────────────────────────────

set_hours_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(cb_day_work, pattern="^daywork_")],
    states={
        HOURS_START: [MessageHandler(filters.TEXT & ~filters.COMMAND, hours_get_start)],
        HOURS_END: [MessageHandler(filters.TEXT & ~filters.COMMAND, hours_get_end)],
    },
    fallbacks=[CommandHandler("cancel", cmd_cancel)],
    per_user=True,
    per_chat=True,
)

service_conv = ConversationHandler(
    entry_points=[
        CallbackQueryHandler(cb_svc_add, pattern="^svcadd$"),
        CallbackQueryHandler(cb_svc_edit, pattern="^svcedit_"),
    ],
    states={
        SVC_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, svc_get_name)],
        SVC_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, svc_get_price)],
        SVC_DURATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, svc_get_duration)],
    },
    fallbacks=[CommandHandler("cancel", cmd_cancel)],
    per_user=True,
    per_chat=True,
)

# Standalone barber callback handlers
barber_callbacks = [
    CallbackQueryHandler(cb_barber_main, pattern="^b_main$"),
    CallbackQueryHandler(cb_requests, pattern="^b_requests$"),
    CallbackQueryHandler(cb_request_detail, pattern="^breq_"),
    CallbackQueryHandler(cb_approve, pattern="^appr_"),
    CallbackQueryHandler(cb_decline, pattern="^decl_"),
    CallbackQueryHandler(cb_schedule, pattern="^b_schedule$"),
    CallbackQueryHandler(cb_day_appointments, pattern="^b_day_appts$"),
    CallbackQueryHandler(cb_day_appt_show, pattern="^dayappt_"),
    CallbackQueryHandler(cb_hours, pattern="^b_hours$"),
    CallbackQueryHandler(cb_edit_day, pattern="^editday_"),
    CallbackQueryHandler(cb_day_off, pattern="^dayoff_"),
    CallbackQueryHandler(cb_services, pattern="^b_services$"),
    CallbackQueryHandler(cb_svc_toggle, pattern="^svctoggle_"),
    CallbackQueryHandler(cb_block, pattern="^b_block$"),
    CallbackQueryHandler(cb_block_date, pattern="^blkdate_"),
    CallbackQueryHandler(cb_block_slot, pattern="^blk_"),
]
