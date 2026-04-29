from datetime import datetime, date, timedelta, time as dtime
import pytz
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
import db

TZ = pytz.timezone("Europe/Moscow")

DAYS_RU_FULL = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
DAYS_RU_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
MONTHS_RU = ["янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]
MONTHS_RU_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня",
                 "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def fmt_date(d: date) -> str:
    dow = DAYS_RU_SHORT[d.weekday()]
    return f"{dow} {d.day} {MONTHS_RU[d.month - 1]}"


def fmt_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt).astimezone(TZ)
    return dt.strftime("%d.%m.%Y в %H:%M")


# ─── Client keyboards ───────────────────────────────────────────────────────

def client_main_menu():
    return ReplyKeyboardMarkup(
        [["✂️ Записаться", "📋 Мои записи"], ["💈 Услуги и цены"]],
        resize_keyboard=True,
    )


def services_kb(services):
    buttons = [
        [InlineKeyboardButton(
            f"{s['name']} — {s['price']} руб. ({s['duration_minutes']} мин)",
            callback_data=f"srv_{s['id']}",
        )]
        for s in services
    ]
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="c_back_main")])
    return InlineKeyboardMarkup(buttons)


def dates_kb(hours_map):
    today = datetime.now(TZ).date()
    buttons, row = [], []
    for i in range(1, 15):
        d = today + timedelta(days=i)
        h = hours_map.get(d.weekday(), {})
        if not h.get("is_working"):
            continue
        row.append(InlineKeyboardButton(fmt_date(d), callback_data=f"date_{d.isoformat()}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    if not buttons:
        buttons.append([InlineKeyboardButton("Нет рабочих дней", callback_data="noop")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="c_back_service")])
    return InlineKeyboardMarkup(buttons)


def times_kb(target_date: date, duration: int, booked_slots, blocked_dts):
    info = db.get_day_hours(target_date.weekday())
    if not info or not info["is_working"]:
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("Нет рабочих слотов", callback_data="noop")],
            [InlineKeyboardButton("◀️ Назад", callback_data="c_back_date")],
        ])

    start = datetime.combine(target_date, info["start_time"])
    end = datetime.combine(target_date, info["end_time"])

    # Build set of occupied 30-min chunks (naive)
    occupied = set()
    for row in booked_slots:
        dt = row["appointment_dt"]
        if hasattr(dt, "tzinfo") and dt.tzinfo:
            dt = dt.replace(tzinfo=None)
        for offset in range(0, row["duration_minutes"], 30):
            occupied.add(dt + timedelta(minutes=offset))
    for bdt in blocked_dts:
        if hasattr(bdt, "tzinfo") and bdt.tzinfo:
            bdt = bdt.replace(tzinfo=None)
        occupied.add(bdt)

    buttons, row = [], []
    slot = start
    while slot + timedelta(minutes=duration) <= end:
        free = all(
            slot + timedelta(minutes=off) not in occupied
            for off in range(0, duration, 30)
        )
        if free:
            row.append(InlineKeyboardButton(slot.strftime("%H:%M"), callback_data=f"time_{slot.strftime('%H:%M')}"))
            if len(row) == 4:
                buttons.append(row)
                row = []
        slot += timedelta(minutes=30)
    if row:
        buttons.append(row)
    if not buttons:
        buttons.append([InlineKeyboardButton("Нет свободных слотов", callback_data="noop")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="c_back_date")])
    return InlineKeyboardMarkup(buttons)


def confirm_booking_kb():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Подтвердить", callback_data="bk_yes"),
        InlineKeyboardButton("❌ Отменить", callback_data="bk_no"),
    ]])


def my_appointments_kb(appointments):
    buttons = [
        [InlineKeyboardButton(
            f"{a['service_name']} — {fmt_dt(a['appointment_dt'])}",
            callback_data=f"myappt_{a['id']}",
        )]
        for a in appointments
    ]
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="c_back_main")])
    return InlineKeyboardMarkup(buttons)


def appt_detail_kb(appt_id, status):
    buttons = []
    if status != "cancelled":
        buttons.append([InlineKeyboardButton("❌ Отменить запись", callback_data=f"cancel_{appt_id}")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="c_my_appts")])
    return InlineKeyboardMarkup(buttons)


def cancel_confirm_kb(appt_id):
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("Да, отменить", callback_data=f"cancelyes_{appt_id}"),
        InlineKeyboardButton("Нет", callback_data=f"myappt_{appt_id}"),
    ]])


# ─── Barber keyboards ────────────────────────────────────────────────────────

def barber_main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Новые заявки", callback_data="b_requests")],
        [InlineKeyboardButton("📅 Расписание", callback_data="b_schedule")],
        [InlineKeyboardButton("✂️ Услуги", callback_data="b_services")],
        [InlineKeyboardButton("🔒 Заблокировать время", callback_data="b_block")],
    ])


def barber_requests_kb(requests):
    buttons = [
        [InlineKeyboardButton(
            f"{a['client_name'] or 'Клиент'} | {a['service_name']} | {fmt_dt(a['appointment_dt'])}",
            callback_data=f"breq_{a['id']}",
        )]
        for a in requests
    ]
    if not requests:
        buttons.append([InlineKeyboardButton("Новых заявок нет", callback_data="noop")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="b_main")])
    return InlineKeyboardMarkup(buttons)


def request_actions_kb(appt_id):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"appr_{appt_id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"decl_{appt_id}"),
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data="b_requests")],
    ])


def barber_schedule_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🕐 Рабочие часы", callback_data="b_hours")],
        [InlineKeyboardButton("📋 Записи на день", callback_data="b_day_appts")],
        [InlineKeyboardButton("◀️ Назад", callback_data="b_main")],
    ])


def working_hours_kb(hours_list):
    buttons = []
    for h in hours_list:
        name = DAYS_RU_FULL[h["day_of_week"]]
        if h["is_working"] and h["start_time"] and h["end_time"]:
            st = h["start_time"].strftime("%H:%M")
            en = h["end_time"].strftime("%H:%M")
            label = f"{name}: {st}–{en}"
        else:
            label = f"{name}: выходной"
        buttons.append([InlineKeyboardButton(label, callback_data=f"editday_{h['day_of_week']}")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="b_schedule")])
    return InlineKeyboardMarkup(buttons)


def day_work_choice_kb(dow):
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Рабочий", callback_data=f"daywork_{dow}"),
            InlineKeyboardButton("❌ Выходной", callback_data=f"dayoff_{dow}"),
        ],
        [InlineKeyboardButton("◀️ Назад", callback_data="b_hours")],
    ])


def select_day_kb(prefix):
    today = datetime.now(TZ).date()
    buttons, row = [], []
    for i in range(8):
        d = today + timedelta(days=i)
        row.append(InlineKeyboardButton(fmt_date(d), callback_data=f"{prefix}_{d.isoformat()}"))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="b_schedule")])
    return InlineKeyboardMarkup(buttons)


def barber_services_kb(services):
    buttons = []
    for s in services:
        status = "" if s["active"] else " [скрыт]"
        row = [
            InlineKeyboardButton(f"{s['name']} — {s['price']} руб.{status}", callback_data=f"svcinfo_{s['id']}"),
            InlineKeyboardButton("✏️", callback_data=f"svcedit_{s['id']}"),
            InlineKeyboardButton("👁" if s["active"] else "👁‍🗨", callback_data=f"svctoggle_{s['id']}"),
        ]
        buttons.append(row)
    buttons.append([InlineKeyboardButton("➕ Добавить услугу", callback_data="svcadd")])
    buttons.append([InlineKeyboardButton("◀️ Назад", callback_data="b_main")])
    return InlineKeyboardMarkup(buttons)


def block_times_kb(target_date: date, booked_slots, blocked_dts):
    info = db.get_day_hours(target_date.weekday())
    back_btn = [InlineKeyboardButton("◀️ Назад", callback_data="b_block")]
    if not info or not info["is_working"]:
        return InlineKeyboardMarkup([[InlineKeyboardButton("День нерабочий", callback_data="noop")], back_btn])

    start = datetime.combine(target_date, info["start_time"])
    end = datetime.combine(target_date, info["end_time"])

    booked_set = set()
    for row in booked_slots:
        dt = row["appointment_dt"]
        if hasattr(dt, "tzinfo") and dt.tzinfo:
            dt = dt.replace(tzinfo=None)
        booked_set.add(dt)

    blocked_set = set()
    for bdt in blocked_dts:
        if hasattr(bdt, "tzinfo") and bdt.tzinfo:
            bdt = bdt.replace(tzinfo=None)
        blocked_set.add(bdt)

    buttons, row = [], []
    slot = start
    while slot < end:
        naive = slot.replace(tzinfo=None) if slot.tzinfo else slot
        if naive in booked_set:
            label = f"🔵 {slot.strftime('%H:%M')}"
            cb = "noop"
        elif naive in blocked_set:
            label = f"🔴 {slot.strftime('%H:%M')}"
            cb = f"blk_{slot.strftime('%H:%M')}"
        else:
            label = slot.strftime("%H:%M")
            cb = f"blk_{slot.strftime('%H:%M')}"
        row.append(InlineKeyboardButton(label, callback_data=cb))
        if len(row) == 4:
            buttons.append(row)
            row = []
        slot += timedelta(minutes=30)
    if row:
        buttons.append(row)
    buttons.append(back_btn)
    return InlineKeyboardMarkup(buttons)
