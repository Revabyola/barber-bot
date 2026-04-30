import os
import logging
import requests as req
import threading
from flask import Flask, request, jsonify
from flask_cors import CORS
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, ContextTypes
import psycopg2
from psycopg2.extras import RealDictCursor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get('DATABASE_URL')
TOKEN = os.environ.get("BARBER_BOT_TOKEN", "")
BARBER_ADMIN_ID = int(os.environ.get("BARBER_ADMIN_ID", "0"))
APP_URL = os.environ.get("BARBER_APP_URL", "")


def get_db():
    return psycopg2.connect(DATABASE_URL, sslmode='require')


def is_admin(user_id):
    return BARBER_ADMIN_ID != 0 and int(user_id) == BARBER_ADMIN_ID


def notify(text):
    if TOKEN and BARBER_ADMIN_ID:
        try:
            req.post(
                f"https://api.telegram.org/bot{TOKEN}/sendMessage",
                json={"chat_id": BARBER_ADMIN_ID, "text": text, "parse_mode": "HTML"},
                timeout=5,
            )
        except Exception as e:
            logger.error(f"Notify failed: {e}")


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS barber_services (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            price INTEGER NOT NULL,
            duration INTEGER DEFAULT 60,
            is_active BOOLEAN DEFAULT TRUE
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS time_slots (
            id SERIAL PRIMARY KEY,
            slot_date DATE NOT NULL,
            slot_time TIME NOT NULL,
            is_booked BOOLEAN DEFAULT FALSE,
            UNIQUE(slot_date, slot_time)
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS appointments (
            id SERIAL PRIMARY KEY,
            slot_id INTEGER REFERENCES time_slots(id) ON DELETE CASCADE,
            client_name TEXT NOT NULL,
            client_phone TEXT DEFAULT '',
            client_telegram_id BIGINT DEFAULT 0,
            service_id INTEGER REFERENCES barber_services(id) ON DELETE SET NULL,
            comment TEXT DEFAULT '',
            status TEXT DEFAULT 'confirmed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS portfolio (
            id SERIAL PRIMARY KEY,
            image_url TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY,
            client_name TEXT NOT NULL,
            client_telegram_id BIGINT DEFAULT 0,
            rating INTEGER DEFAULT 5 CHECK(rating BETWEEN 1 AND 5),
            review_text TEXT NOT NULL,
            is_approved BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cur.close()
    conn.close()
    logger.info("DB initialized")


@app.route('/health')
def health():
    return "OK", 200


@app.route('/api/barber/me')
def check_me():
    user_id = request.args.get('user_id', 0)
    return jsonify({'is_admin': is_admin(user_id)})


# --- Services ---

@app.route('/api/barber/services', methods=['GET'])
def get_services():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM barber_services WHERE is_active = TRUE ORDER BY price")
    services = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify({'services': services})


@app.route('/api/barber/services', methods=['POST'])
def create_service():
    data = request.get_json()
    if not is_admin(data.get('user_id', 0)):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO barber_services (name, description, price, duration) VALUES (%s,%s,%s,%s) RETURNING id",
        (data['name'], data.get('description', ''), data['price'], data.get('duration', 60))
    )
    sid = cur.fetchone()[0]
    conn.commit(); cur.close(); conn.close()
    return jsonify({'success': True, 'id': sid})


@app.route('/api/barber/services/<int:sid>', methods=['DELETE'])
def delete_service(sid):
    if not is_admin(request.args.get('user_id', 0)):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE barber_services SET is_active = FALSE WHERE id = %s", (sid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({'success': True})


# --- Slots ---

@app.route('/api/barber/slots', methods=['GET'])
def get_slots():
    user_id = request.args.get('user_id', 0)
    show_all = request.args.get('all', '0') == '1' and is_admin(user_id)
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if show_all:
        cur.execute("""
            SELECT ts.id, ts.slot_date, ts.slot_time, ts.is_booked,
                   a.client_name, a.client_phone, a.comment, bs.name as service_name
            FROM time_slots ts
            LEFT JOIN appointments a ON ts.id = a.slot_id
            LEFT JOIN barber_services bs ON a.service_id = bs.id
            WHERE ts.slot_date >= CURRENT_DATE
            ORDER BY ts.slot_date, ts.slot_time
        """)
    else:
        cur.execute("""
            SELECT id, slot_date, slot_time
            FROM time_slots
            WHERE slot_date >= CURRENT_DATE AND is_booked = FALSE
            ORDER BY slot_date, slot_time
        """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    result = []
    for s in rows:
        item = {'id': s['id'], 'date': s['slot_date'].isoformat(), 'time': str(s['slot_time'])[:5]}
        if show_all:
            item.update({
                'is_booked': s['is_booked'],
                'client_name': s.get('client_name'),
                'client_phone': s.get('client_phone'),
                'service_name': s.get('service_name'),
                'comment': s.get('comment'),
            })
        result.append(item)
    return jsonify({'slots': result})


@app.route('/api/barber/slots', methods=['POST'])
def create_slot():
    data = request.get_json()
    if not is_admin(data.get('user_id', 0)):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO time_slots (slot_date, slot_time) VALUES (%s,%s) RETURNING id",
            (data['date'], data['time'])
        )
        sid = cur.fetchone()[0]
        conn.commit()
        return jsonify({'success': True, 'id': sid})
    except Exception as e:
        conn.rollback()
        return jsonify({'success': False, 'error': str(e)})
    finally:
        cur.close(); conn.close()


@app.route('/api/barber/slots/<int:sid>', methods=['DELETE'])
def delete_slot(sid):
    if not is_admin(request.args.get('user_id', 0)):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM time_slots WHERE id = %s AND is_booked = FALSE", (sid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({'success': True})


# --- Appointments ---

@app.route('/api/barber/appointments', methods=['GET'])
def get_appointments():
    user_id = request.args.get('user_id', 0)
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    if is_admin(user_id):
        cur.execute("""
            SELECT a.id, a.client_name, a.client_phone, a.comment, a.status,
                   ts.slot_date, ts.slot_time, bs.name as service_name, bs.price
            FROM appointments a
            JOIN time_slots ts ON a.slot_id = ts.id
            LEFT JOIN barber_services bs ON a.service_id = bs.id
            WHERE ts.slot_date >= CURRENT_DATE
            ORDER BY ts.slot_date, ts.slot_time
        """)
    else:
        cur.execute("""
            SELECT a.id, a.status, ts.slot_date, ts.slot_time,
                   bs.name as service_name, bs.price
            FROM appointments a
            JOIN time_slots ts ON a.slot_id = ts.id
            LEFT JOIN barber_services bs ON a.service_id = bs.id
            WHERE a.client_telegram_id = %s AND ts.slot_date >= CURRENT_DATE
            ORDER BY ts.slot_date, ts.slot_time
        """, (user_id,))
    rows = cur.fetchall()
    cur.close(); conn.close()
    result = []
    for a in rows:
        item = {
            'id': a['id'], 'date': a['slot_date'].isoformat(),
            'time': str(a['slot_time'])[:5], 'service_name': a['service_name'],
            'price': a['price'], 'status': a['status'],
        }
        if is_admin(user_id):
            item.update({'client_name': a['client_name'], 'client_phone': a['client_phone'], 'comment': a['comment']})
        result.append(item)
    return jsonify({'appointments': result})


@app.route('/api/barber/appointments', methods=['POST'])
def create_appointment():
    data = request.get_json()
    slot_id = data.get('slot_id')
    client_name = data.get('client_name', '').strip()
    if not slot_id or not client_name:
        return jsonify({'success': False, 'error': 'Missing fields'}), 400
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM time_slots WHERE id = %s AND is_booked = FALSE FOR UPDATE", (slot_id,))
    slot = cur.fetchone()
    if not slot:
        cur.close(); conn.close()
        return jsonify({'success': False, 'error': 'Slot not available'}), 409
    service = None
    service_id = data.get('service_id')
    if service_id:
        cur.execute("SELECT * FROM barber_services WHERE id = %s", (service_id,))
        service = cur.fetchone()
    cur2 = conn.cursor()
    cur2.execute("""
        INSERT INTO appointments (slot_id, client_name, client_phone, client_telegram_id, service_id, comment)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING id
    """, (slot_id, client_name, data.get('client_phone', ''), data.get('client_telegram_id', 0),
          service_id, data.get('comment', '')))
    appt_id = cur2.fetchone()[0]
    cur2.execute("UPDATE time_slots SET is_booked = TRUE WHERE id = %s", (slot_id,))
    conn.commit(); cur.close(); cur2.close(); conn.close()
    date_str = slot['slot_date'].strftime('%d.%m.%Y')
    time_str = str(slot['slot_time'])[:5]
    svc = service['name'] if service else 'не указана'
    phone = data.get('client_phone', '') or 'не указан'
    msg = f"✂️ <b>Новая запись!</b>\n\n👤 {client_name}\n📱 {phone}\n📅 {date_str} в {time_str}\n💈 {svc}"
    if data.get('comment'):
        msg += f"\n💬 {data['comment']}"
    notify(msg)
    return jsonify({'success': True, 'appointment_id': appt_id})


@app.route('/api/barber/appointments/<int:aid>', methods=['DELETE'])
def cancel_appointment(aid):
    user_id = int(request.args.get('user_id', 0))
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM appointments WHERE id = %s", (aid,))
    appt = cur.fetchone()
    if not appt:
        cur.close(); conn.close()
        return jsonify({'success': False}), 404
    if not is_admin(user_id) and user_id != appt['client_telegram_id']:
        cur.close(); conn.close()
        return jsonify({'error': 'Unauthorized'}), 403
    cur2 = conn.cursor()
    cur2.execute("DELETE FROM appointments WHERE id = %s", (aid,))
    cur2.execute("UPDATE time_slots SET is_booked = FALSE WHERE id = %s", (appt['slot_id'],))
    conn.commit(); cur.close(); cur2.close(); conn.close()
    return jsonify({'success': True})


# --- Portfolio ---

@app.route('/api/barber/portfolio', methods=['GET'])
def get_portfolio():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM portfolio ORDER BY created_at DESC")
    items = [dict(r) for r in cur.fetchall()]
    cur.close(); conn.close()
    return jsonify({'portfolio': items})


@app.route('/api/barber/portfolio', methods=['POST'])
def add_portfolio():
    data = request.get_json()
    if not is_admin(data.get('user_id', 0)):
        return jsonify({'error': 'Unauthorized'}), 403
    image_url = data.get('image_url', '').strip()
    if not image_url:
        return jsonify({'success': False}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute("INSERT INTO portfolio (image_url, description) VALUES (%s,%s) RETURNING id",
                (image_url, data.get('description', '')))
    pid = cur.fetchone()[0]
    conn.commit(); cur.close(); conn.close()
    return jsonify({'success': True, 'id': pid})


@app.route('/api/barber/portfolio/<int:pid>', methods=['DELETE'])
def delete_portfolio(pid):
    if not is_admin(request.args.get('user_id', 0)):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM portfolio WHERE id = %s", (pid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({'success': True})


# --- Reviews ---

@app.route('/api/barber/reviews', methods=['GET'])
def get_reviews():
    conn = get_db()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM reviews WHERE is_approved = TRUE ORDER BY created_at DESC LIMIT 50")
    rows = cur.fetchall()
    cur.close(); conn.close()
    result = [{'id': r['id'], 'client_name': r['client_name'], 'rating': r['rating'],
               'text': r['review_text'], 'date': r['created_at'].strftime('%d.%m.%Y')} for r in rows]
    return jsonify({'reviews': result})


@app.route('/api/barber/reviews', methods=['POST'])
def add_review():
    data = request.get_json()
    client_name = data.get('client_name', '').strip()
    text = data.get('text', '').strip()
    if not client_name or not text:
        return jsonify({'success': False}), 400
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO reviews (client_name, client_telegram_id, rating, review_text) VALUES (%s,%s,%s,%s) RETURNING id",
        (client_name, data.get('client_telegram_id', 0), data.get('rating', 5), text)
    )
    rid = cur.fetchone()[0]
    conn.commit(); cur.close(); conn.close()
    return jsonify({'success': True, 'id': rid})


@app.route('/api/barber/reviews/<int:rid>', methods=['DELETE'])
def delete_review(rid):
    if not is_admin(request.args.get('user_id', 0)):
        return jsonify({'error': 'Unauthorized'}), 403
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM reviews WHERE id = %s", (rid,))
    conn.commit(); cur.close(); conn.close()
    return jsonify({'success': True})


# --- Telegram bot ---

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("✂️ Открыть приложение", web_app=WebAppInfo(url=APP_URL))]]
    await update.message.reply_text(
        "💈 Привет! Нажми кнопку ниже, чтобы записаться к барберу:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


if __name__ == "__main__":
    def run_flask():
        port = int(os.environ.get('PORT', 10000))
        logger.info(f"Flask running on port {port}")
        app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()

    if TOKEN:
        init_db()
        bot_app = Application.builder().token(TOKEN).build()
        bot_app.add_handler(CommandHandler("start", start_cmd))
        logger.info("Barber bot running!")
        bot_app.run_polling()
    else:
        logger.error("BARBER_BOT_TOKEN not set!")
