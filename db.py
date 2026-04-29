import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import date, timedelta

DATABASE_URL = os.environ["DATABASE_URL"]


def _conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def init_db():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS services (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(100) NOT NULL,
                    price INTEGER NOT NULL,
                    duration_minutes INTEGER NOT NULL DEFAULT 30,
                    active BOOLEAN DEFAULT TRUE
                );

                CREATE TABLE IF NOT EXISTS working_hours (
                    day_of_week INTEGER PRIMARY KEY,
                    start_time TIME,
                    end_time TIME,
                    is_working BOOLEAN DEFAULT FALSE
                );

                CREATE TABLE IF NOT EXISTS appointments (
                    id SERIAL PRIMARY KEY,
                    client_id BIGINT NOT NULL,
                    client_name VARCHAR(200),
                    client_username VARCHAR(100),
                    service_id INTEGER REFERENCES services(id),
                    service_name VARCHAR(100),
                    appointment_dt TIMESTAMP NOT NULL,
                    duration_minutes INTEGER NOT NULL DEFAULT 30,
                    status VARCHAR(20) DEFAULT 'pending',
                    reminder_1day_sent BOOLEAN DEFAULT FALSE,
                    reminder_2hour_sent BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS blocked_slots (
                    id SERIAL PRIMARY KEY,
                    block_dt TIMESTAMP NOT NULL UNIQUE
                );
            """)
            for day in range(7):
                cur.execute("""
                    INSERT INTO working_hours (day_of_week, start_time, end_time, is_working)
                    VALUES (%s, '10:00', '20:00', %s)
                    ON CONFLICT (day_of_week) DO NOTHING
                """, (day, day < 6))
        conn.commit()


# --- Services ---

def get_services(active_only=True):
    with _conn() as conn:
        with conn.cursor() as cur:
            if active_only:
                cur.execute("SELECT * FROM services WHERE active = TRUE ORDER BY id")
            else:
                cur.execute("SELECT * FROM services ORDER BY id")
            return cur.fetchall()


def get_service(service_id):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM services WHERE id = %s", (service_id,))
            return cur.fetchone()


def add_service(name, price, duration):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO services (name, price, duration_minutes) VALUES (%s, %s, %s) RETURNING id",
                (name, price, duration),
            )
            result = cur.fetchone()
        conn.commit()
        return result["id"]


def update_service(service_id, name, price, duration):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE services SET name=%s, price=%s, duration_minutes=%s WHERE id=%s",
                (name, price, duration, service_id),
            )
        conn.commit()


def toggle_service_active(service_id):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE services SET active = NOT active WHERE id=%s RETURNING active",
                (service_id,),
            )
            result = cur.fetchone()
        conn.commit()
        return result["active"]


# --- Working hours ---

def get_working_hours():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM working_hours ORDER BY day_of_week")
            return cur.fetchall()


def get_day_hours(day_of_week):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM working_hours WHERE day_of_week=%s", (day_of_week,))
            return cur.fetchone()


def set_day_hours(day_of_week, is_working, start_time=None, end_time=None):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE working_hours SET is_working=%s, start_time=%s, end_time=%s WHERE day_of_week=%s",
                (is_working, start_time, end_time, day_of_week),
            )
        conn.commit()


# --- Appointments ---

def create_appointment(client_id, client_name, client_username, service_id, service_name, appointment_dt, duration):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO appointments
                    (client_id, client_name, client_username, service_id, service_name, appointment_dt, duration_minutes)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            """, (client_id, client_name, client_username, service_id, service_name, appointment_dt, duration))
            result = cur.fetchone()
        conn.commit()
        return result["id"]


def get_appointment(appt_id):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM appointments WHERE id=%s", (appt_id,))
            return cur.fetchone()


def get_pending_appointments():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM appointments
                WHERE status='pending' AND appointment_dt > NOW()
                ORDER BY appointment_dt
            """)
            return cur.fetchall()


def get_client_appointments(client_id):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM appointments
                WHERE client_id=%s AND appointment_dt > NOW() AND status != 'cancelled'
                ORDER BY appointment_dt
            """, (client_id,))
            return cur.fetchall()


def get_appointments_for_day(target_date):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM appointments
                WHERE DATE(appointment_dt) = %s AND status = 'confirmed'
                ORDER BY appointment_dt
            """, (target_date,))
            return cur.fetchall()


def get_booked_slots(target_date):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT appointment_dt, duration_minutes FROM appointments
                WHERE DATE(appointment_dt) = %s AND status IN ('confirmed', 'pending')
            """, (target_date,))
            return cur.fetchall()


def get_upcoming_confirmed():
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM appointments
                WHERE status='confirmed' AND appointment_dt > NOW()
                ORDER BY appointment_dt
            """)
            return cur.fetchall()


def update_appointment_status(appt_id, status):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE appointments SET status=%s WHERE id=%s", (status, appt_id))
        conn.commit()


def mark_reminder_sent(appt_id, reminder_type):
    col = "reminder_1day_sent" if reminder_type == "1day" else "reminder_2hour_sent"
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f"UPDATE appointments SET {col}=TRUE WHERE id=%s", (appt_id,))
        conn.commit()


# --- Blocked slots ---

def get_blocked_slots_for_date(target_date):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT block_dt FROM blocked_slots WHERE DATE(block_dt) = %s", (target_date,))
            return [row["block_dt"] for row in cur.fetchall()]


def toggle_blocked_slot(slot_dt):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM blocked_slots WHERE block_dt=%s", (slot_dt,))
            existing = cur.fetchone()
            if existing:
                cur.execute("DELETE FROM blocked_slots WHERE block_dt=%s", (slot_dt,))
                blocked = False
            else:
                cur.execute("INSERT INTO blocked_slots (block_dt) VALUES (%s)", (slot_dt,))
                blocked = True
        conn.commit()
        return blocked
