from flask import Flask, render_template, request, make_response, redirect, url_for
from models import Admin, Bus
from booking_manager import BookingManager
import psutil
import os
import sqlite3
import uuid
import time
from datetime import datetime

app = Flask(__name__)

admin = Admin("admin", "zoho123")
manager = BookingManager()
process = psutil.Process(os.getpid())
resource_metrics = {
    "max_cpu_usage": 0.0,
    "max_physical_memory": 0.0,
    "max_virtual_memory": 0.0,
}
prev_cpu_times = psutil.cpu_times()
DB_PATH = os.path.join(os.path.dirname(__file__), "visitors.db")


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS visitors (
                visitor_id TEXT PRIMARY KEY,
                device_type TEXT NOT NULL,
                user_agent TEXT,
                ip_address TEXT,
                role TEXT NOT NULL DEFAULT 'user',
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS visits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                visitor_id TEXT NOT NULL,
                device_type TEXT NOT NULL,
                user_agent TEXT,
                ip_address TEXT,
                role TEXT NOT NULL DEFAULT 'user',
                visited_at TEXT NOT NULL
            )
        """)
        existing_visitor_columns = [row[1] for row in conn.execute("PRAGMA table_info(visitors)")]
        if 'role' not in existing_visitor_columns:
            conn.execute("ALTER TABLE visitors ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        existing_visit_columns = [row[1] for row in conn.execute("PRAGMA table_info(visits)")]
        if 'role' not in existing_visit_columns:
            conn.execute("ALTER TABLE visits ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
        conn.commit()


def get_device_type(user_agent):
    ua = (user_agent or "").lower()
    if "ipad" in ua or "tablet" in ua:
        return "Tablet"
    if "mobile" in ua or "android" in ua or "iphone" in ua or "windows phone" in ua:
        return "Mobile"
    return "Desktop"


def get_client_ip():
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def track_visitor(role='user'):
    visitor_id = request.cookies.get("visitor_id")
    if not visitor_id:
        visitor_id = str(uuid.uuid4())

    device_type = get_device_type(request.headers.get("User-Agent", ""))
    ip_address = get_client_ip()
    now = datetime.utcnow().isoformat()
    user_agent = request.headers.get("User-Agent", "")

    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        existing = conn.execute("SELECT 1 FROM visitors WHERE visitor_id = ?", (visitor_id,)).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO visitors (visitor_id, device_type, user_agent, ip_address, role, first_seen, last_seen) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (visitor_id, device_type, user_agent, ip_address, role, now, now),
            )
        else:
            conn.execute(
                "UPDATE visitors SET last_seen = ?, device_type = ?, user_agent = ?, ip_address = ?, role = ? WHERE visitor_id = ?",
                (now, device_type, user_agent, ip_address, role, visitor_id),
            )

        conn.execute(
            "INSERT INTO visits (visitor_id, device_type, user_agent, ip_address, role, visited_at) VALUES (?, ?, ?, ?, ?, ?)",
            (visitor_id, device_type, user_agent, ip_address, role, now),
        )
        conn.commit()

    return visitor_id


def get_visitor_stats():
    today = datetime.utcnow().date().isoformat()
    init_db()
    with sqlite3.connect(DB_PATH) as conn:
        visitor_count = conn.execute(
            "SELECT COUNT(DISTINCT visitor_id) FROM visits WHERE DATE(visited_at) = ? AND role != 'admin'",
            (today,)
        ).fetchone()[0]
        device_counts = {
            "Desktop": conn.execute(
                "SELECT COUNT(DISTINCT visitor_id) FROM visits WHERE DATE(visited_at) = ? AND device_type = 'Desktop' AND role != 'admin'",
                (today,)
            ).fetchone()[0],
            "Mobile": conn.execute(
                "SELECT COUNT(DISTINCT visitor_id) FROM visits WHERE DATE(visited_at) = ? AND device_type = 'Mobile' AND role != 'admin'",
                (today,)
            ).fetchone()[0],
            "Tablet": conn.execute(
                "SELECT COUNT(DISTINCT visitor_id) FROM visits WHERE DATE(visited_at) = ? AND device_type = 'Tablet' AND role != 'admin'",
                (today,)
            ).fetchone()[0],
        }
    return visitor_count, device_counts


def get_current_resource_metrics():
    global prev_cpu_times
    cpu = psutil.cpu_percent(interval=0.1)
    current_cpu_times = psutil.cpu_times()
    idle_seconds = max(0.0, current_cpu_times.idle - prev_cpu_times.idle)
    prev_cpu_times = current_cpu_times

    physical_memory = process.memory_info().rss / 1024 / 1024
    virtual_memory = process.memory_info().vms / 1024 / 1024

    resource_metrics["max_cpu_usage"] = max(resource_metrics["max_cpu_usage"], cpu)
    resource_metrics["max_physical_memory"] = max(resource_metrics["max_physical_memory"], physical_memory)
    resource_metrics["max_virtual_memory"] = max(resource_metrics["max_virtual_memory"], virtual_memory)

    return {
        "cpu_idle_time": round(idle_seconds, 3),
        "max_cpu_usage": round(resource_metrics["max_cpu_usage"], 1),
        "max_physical_memory": round(resource_metrics["max_physical_memory"], 2),
        "max_virtual_memory": round(resource_metrics["max_virtual_memory"], 2),
    }


def get_seat_info(bus, journey_date, visitor_id):
    seats = bus.get_seats_for_date(journey_date)
    seat_infos = []

    with manager.lock:
        for seat in seats:
            manager._check_and_unlock(seat)
            locked_remaining = 0
            if seat.status == "LOCKED" and seat.lock_time:
                elapsed = time.time() - seat.lock_time
                locked_remaining = max(0, int(300 - elapsed))
            seat_infos.append({
                "seat_number": seat.seat_number,
                "status": seat.status,
                "locked_by_current": seat.status == "LOCKED" and seat.locked_by == visitor_id,
                "booked_by_current": seat.status == "BOOKED" and getattr(seat, "booked_by", None) == visitor_id,
                "locked_remaining": locked_remaining,
            })

    return seat_infos



init_db()

# -----------------------------
# Create Initial Buses
# -----------------------------

bus_data = [

("BUS001","Chennai","Coimbatore","06:00 AM","01:00 PM",650),
("BUS002","Chennai","Madurai","07:00 AM","03:00 PM",700),
("BUS003","Chennai","Salem","08:00 AM","01:30 PM",450),
("BUS004","Chennai","Trichy","09:00 AM","03:00 PM",550),
("BUS005","Chennai","Erode","10:00 AM","05:00 PM",620),
("BUS006","Chennai","Vellore","06:30 AM","09:30 AM",300),
("BUS007","Chennai","Tirunelveli","05:30 AM","03:30 PM",900),
("BUS008","Chennai","Karur","07:30 AM","02:00 PM",500),
("BUS009","Chennai","Kanyakumari","04:30 AM","05:30 PM",1200),
("BUS010","Chennai","Thanjavur","09:30 AM","04:00 PM",600)

]

for bus in bus_data:

    manager.add_bus(

        Bus(
            bus[0],
            bus[1],
            bus[2],
            bus[3],
            bus[4],
            bus[5],
            40
        )

    )

# -----------------------------
# Routes
# -----------------------------

@app.route("/")
def home():
    visitor_id = track_visitor('user')
    response = make_response(render_template("login.html"))
    response.set_cookie("visitor_id", visitor_id, httponly=True, samesite="Lax")
    return response


@app.route("/login", methods=["POST"])
def login():

    username = request.form.get("username", "")
    password = request.form.get("password", "")
    role = request.form.get("role", "user")

    if role == "admin":
        if not username or not password:
            return "Admin username and password are required ❌"
        if not admin.login(username, password):
            return "Invalid Credentials ❌"
    elif role == "user":
        pass
    else:
        return "Invalid role ❌"

    visitor_id = track_visitor(role)

    visitor_count, device_counts = get_visitor_stats()
    resource_stats = get_current_resource_metrics()

    response = make_response(render_template(

        "dashboard.html",

        visitor_count=visitor_count,

        device_counts=device_counts,

        total_buses=len(manager.buses),

        cpu_idle_time=resource_stats["cpu_idle_time"],

        max_cpu_usage=resource_stats["max_cpu_usage"],

        max_physical_memory=resource_stats["max_physical_memory"],

        max_virtual_memory=resource_stats["max_virtual_memory"],

        buses=manager.buses.values(),
 
        journey_date="2026-07-01",

        user_role=role,

        merge_message=None,

        merge_alert_buses=manager.merge_alert_buses,

        can_undo_merge=manager.can_undo_merge() if hasattr(manager, 'can_undo_merge') else False

    ))
    response.set_cookie("visitor_id", visitor_id, httponly=True, samesite="Lax")
    response.set_cookie("user_role", role, httponly=True, samesite="Lax")
    return response


@app.route("/seats/<bus_id>")
def seats(bus_id):

    visitor_id = request.cookies.get("visitor_id")
    if not visitor_id:
        visitor_id = track_visitor('user')

    bus = manager.buses.get(bus_id)
    if not bus:
        return "Bus Not Found"

    if bus_id in manager.merge_alert_buses:
        return "Bus alteration in process"

    journey_date = request.args.get("date") or datetime.utcnow().strftime("%Y-%m-%d")
    today_date = datetime.utcnow().strftime("%Y-%m-%d")
    seat_infos = get_seat_info(bus, journey_date, visitor_id)
    seat_rows = [seat_infos[i:i+4] for i in range(0, len(seat_infos), 4)]

    response = make_response(render_template(
        "seats.html",
        bus=bus,
        seat_rows=seat_rows,
        visitor_id=visitor_id,
        journey_date=journey_date,
        today_date=today_date
    ))
    response.set_cookie("visitor_id", visitor_id, httponly=True, samesite="Lax")
    return response


@app.route("/seat-action/<bus_id>/<int:seat_number>", methods=["POST"])
def seat_action(bus_id, seat_number):
    visitor_id = request.cookies.get("visitor_id")
    if not visitor_id:
        visitor_id = track_visitor('user')

    journey_date = request.form.get("journey_date", datetime.utcnow().strftime("%Y-%m-%d"))
    action = request.form.get("action")
    if action == "lock":
        manager.select_seat(bus_id, journey_date, seat_number, visitor_id)
    elif action == "book":
        booking_id = f"BK-{seat_number}-{int(time.time())}"
        manager.book_seat(bus_id, journey_date, seat_number, visitor_id, booking_id)
    elif action == "cancel":
        manager.cancel_booking(bus_id, journey_date, seat_number, visitor_id)
    else:
        return "Invalid booking action"

    response = redirect(url_for("seats", bus_id=bus_id, date=journey_date))
    response.set_cookie("visitor_id", visitor_id, httponly=True, samesite="Lax")
    return response


@app.route("/seat-action/<bus_id>", methods=["POST"])
def seat_action_multi(bus_id):
    visitor_id = request.cookies.get("visitor_id")
    if not visitor_id:
        visitor_id = track_visitor('user')

    journey_date = request.form.get("journey_date", datetime.utcnow().strftime("%Y-%m-%d"))
    action = request.form.get("action")
    selected_seats = request.form.get("selected_seats", "")
    seat_numbers = [int(s) for s in selected_seats.split(",") if s.strip().isdigit()]

    if not seat_numbers:
        return "No seats selected"

    if action == "lock":
        for seat_number in seat_numbers:
            manager.select_seat(bus_id, journey_date, seat_number, visitor_id)
    elif action == "book":
        bus = manager.buses.get(bus_id)
        if not bus:
            return "Bus not found"
        for seat_number in seat_numbers:
            seats = bus.get_seats_for_date(journey_date)
            seat = seats[seat_number - 1]
            if seat.status == "AVAILABLE":
                manager.select_seat(bus_id, journey_date, seat_number, visitor_id)
            if seat.locked_by == visitor_id:
                booking_id = f"BK-{seat_number}-{int(time.time())}"
                manager.book_seat(bus_id, journey_date, seat_number, visitor_id, booking_id)
    elif action == "cancel":
        for seat_number in seat_numbers:
            manager.cancel_booking(bus_id, journey_date, seat_number, visitor_id)
    else:
        return "Invalid booking action"

    response = redirect(url_for("seats", bus_id=bus_id, date=journey_date))
    response.set_cookie("visitor_id", visitor_id, httponly=True, samesite="Lax")
    return response


@app.route("/merge-buses", methods=["POST"])
def merge_buses():
    user_role = request.cookies.get("user_role", "user")
    if user_role != "admin":
        return "Admin access required to merge buses ❌"

    merge_message = manager.merge_buses()
    merge_alert_buses = set() if merge_message.startswith("Merged into") else manager.merge_alert_buses
    visitor_id = request.cookies.get("visitor_id")
    if not visitor_id:
        visitor_id = track_visitor('admin')

    visitor_count, device_counts = get_visitor_stats()
    resource_stats = get_current_resource_metrics()

    response = make_response(render_template(
        "dashboard.html",
        visitor_count=visitor_count,
        device_counts=device_counts,
        total_buses=len(manager.buses),
        cpu_idle_time=resource_stats["cpu_idle_time"],
        max_cpu_usage=resource_stats["max_cpu_usage"],
        max_physical_memory=resource_stats["max_physical_memory"],
        max_virtual_memory=resource_stats["max_virtual_memory"],
        buses=manager.buses.values(),
        journey_date="2026-07-01",
        user_role="admin",
        merge_message=merge_message,
        can_undo_merge=manager.can_undo_merge(),
        merge_alert_buses=merge_alert_buses
    ))
    response.set_cookie("visitor_id", visitor_id, httponly=True, samesite="Lax")
    response.set_cookie("user_role", "admin", httponly=True, samesite="Lax")
    return response

@app.route("/undo-merge", methods=["POST"])
def undo_merge():
    user_role = request.cookies.get("user_role", "user")
    if user_role != "admin":
        return "Admin access required to undo merge ❌"

    undo_message = manager.undo_merge()
    merge_alert_buses = set() if undo_message.startswith("Merge undone") else manager.merge_alert_buses
    visitor_id = request.cookies.get("visitor_id")
    if not visitor_id:
        visitor_id = track_visitor('admin')

    visitor_count, device_counts = get_visitor_stats()
    resource_stats = get_current_resource_metrics()

    response = make_response(render_template(
        "dashboard.html",
        visitor_count=visitor_count,
        device_counts=device_counts,
        total_buses=len(manager.buses),
        cpu_idle_time=resource_stats["cpu_idle_time"],
        max_cpu_usage=resource_stats["max_cpu_usage"],
        max_physical_memory=resource_stats["max_physical_memory"],
        max_virtual_memory=resource_stats["max_virtual_memory"],
        buses=manager.buses.values(),
        journey_date="2026-07-01",
        user_role="admin",
        merge_message=undo_message,
        can_undo_merge=manager.can_undo_merge(),
        merge_alert_buses=merge_alert_buses
    ))
    response.set_cookie("visitor_id", visitor_id, httponly=True, samesite="Lax")
    response.set_cookie("user_role", "admin", httponly=True, samesite="Lax")
    return response
if __name__ == "__main__":
    app.run(debug=True)