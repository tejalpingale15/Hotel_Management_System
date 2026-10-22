import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (Flask, flash, g, redirect, render_template, request,
                   session, url_for)

BASE = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE, "hotel.db")
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "adminpass")

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-change-me")

AMENITIES = {
    "Single": ["One single bed", "Free Wi-Fi", "Work desk", "Air conditioning"],
    "Double": ["Queen bed", "Free Wi-Fi", "Breakfast included", "Air conditioning"],
    "Deluxe": ["King bed", "City view", "Mini bar", "Breakfast included"],
    "Suite": ["King bed and lounge", "Private balcony", "Bathtub", "Breakfast and dinner"],
}
DEFAULT_AMENITIES = ["Free Wi-Fi", "Air conditioning", "Daily housekeeping"]


# ---------- database (SQLite: built into Python, no server or password) ----------
def db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_FILE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


@app.teardown_appcontext
def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def seed(conn):
    rooms = [("101", "Single", 1200), ("102", "Single", 1200),
             ("103", "Double", 2000), ("104", "Double", 2000),
             ("201", "Deluxe", 3500), ("202", "Deluxe", 3500),
             ("301", "Suite", 5000), ("302", "Suite", 6500)]
    conn.executemany("INSERT INTO rooms (room_number, room_type, price) VALUES (?,?,?)", rooms)
    today = date.today()
    # room, guest, email, phone, check-in offset (days), nights, status
    guests = [
        ("102", "Aarav Sharma", "aarav.sharma@example.com", "9876501234", 0, 3, "active"),
        ("104", "Priya Deshmukh", "priya.d@example.com", "9822012345", 1, 2, "active"),
        ("202", "Rohan Kulkarni", "rohan.k@example.com", "9890098765", -1, 4, "active"),
        ("101", "Sneha Patil", "sneha.patil@example.com", "9765432101", -6, 2, "checked_out"),
    ]
    for number, name, email, phone, offset, nights, status in guests:
        room = conn.execute("SELECT id, price FROM rooms WHERE room_number=?", (number,)).fetchone()
        ci = today + timedelta(days=offset)
        co = ci + timedelta(days=nights)
        conn.execute(
            "INSERT INTO bookings (room_id, customer_name, customer_email, customer_phone,"
            " check_in, check_out, nights, total, status) VALUES (?,?,?,?,?,?,?,?,?)",
            (room[0], name, email, phone, ci.isoformat(), co.isoformat(), nights, nights * room[1], status))
        if status == "active":
            conn.execute("UPDATE rooms SET status='booked' WHERE id=?", (room[0],))


def init_db():
    conn = sqlite3.connect(DB_FILE)
    with open(os.path.join(BASE, "schema.sql"), encoding="utf-8") as f:
        conn.executescript(f.read())
    if conn.execute("SELECT COUNT(*) FROM rooms").fetchone()[0] == 0:
        seed(conn)
    conn.commit()
    conn.close()


# ---------- template helpers ----------
@app.template_filter("inr")
def inr(value):
    return "₹{:,.0f}".format(value or 0)


@app.template_filter("pretty_date")
def pretty_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %b %Y")
    except (TypeError, ValueError):
        return value


app.jinja_env.globals["amenities"] = lambda t: AMENITIES.get(t, DEFAULT_AMENITIES)


def admin_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return wrapped


# ---------- guest pages ----------
@app.route("/")
def index():
    rtype = request.args.get("type", "")
    d = db()
    types = [r[0] for r in d.execute("SELECT room_type FROM rooms GROUP BY room_type ORDER BY MIN(price)")]
    sql, args = "SELECT * FROM rooms WHERE status='available'", []
    if rtype:
        sql += " AND room_type=?"
        args.append(rtype)
    rooms = d.execute(sql + " ORDER BY price, room_number", args).fetchall()
    totals = d.execute("SELECT COUNT(*), SUM(status='available') FROM rooms").fetchone()
    return render_template("index.html", rooms=rooms, types=types, rtype=rtype,
                           total_rooms=totals[0], free_rooms=totals[1] or 0)


@app.route("/room/<int:room_id>")
def room_detail(room_id):
    room = db().execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
    if not room:
        flash("We could not find that room.", "danger")
        return redirect(url_for("index"))
    return render_template("room.html", room=room)


@app.route("/book/<int:room_id>", methods=["GET", "POST"])
def book_room(room_id):
    d = db()
    room = d.execute("SELECT * FROM rooms WHERE id=? AND status='available'", (room_id,)).fetchone()
    if not room:
        flash("That room is no longer available. Pick another one.", "warning")
        return redirect(url_for("index"))
    form = {}
    if request.method == "POST":
        form = {k: request.form.get(k, "").strip() for k in ("name", "email", "phone", "checkin", "checkout")}
        try:
            ci = datetime.strptime(form["checkin"], "%Y-%m-%d").date()
            co = datetime.strptime(form["checkout"], "%Y-%m-%d").date()
        except ValueError:
            flash("Enter a valid check-in and check-out date.", "danger")
        else:
            if not form["name"]:
                flash("Enter the guest name.", "danger")
            elif ci < date.today():
                flash("Check-in cannot be in the past.", "danger")
            elif co <= ci:
                flash("Check-out must be after check-in.", "danger")
            else:
                nights = (co - ci).days
                cur = d.execute(
                    "INSERT INTO bookings (room_id, customer_name, customer_email, customer_phone,"
                    " check_in, check_out, nights, total) VALUES (?,?,?,?,?,?,?,?)",
                    (room_id, form["name"], form["email"], form["phone"],
                     ci.isoformat(), co.isoformat(), nights, nights * room["price"]))
                d.execute("UPDATE rooms SET status='booked' WHERE id=?", (room_id,))
                d.commit()
                return redirect(url_for("booking_confirmation", booking_id=cur.lastrowid))
    return render_template("book.html", room=room, form=form, today=date.today().isoformat())


@app.route("/booking/<int:booking_id>")
def booking_confirmation(booking_id):
    b = db().execute("SELECT b.*, r.room_number, r.room_type FROM bookings b "
                     "JOIN rooms r ON r.id=b.room_id WHERE b.id=?", (booking_id,)).fetchone()
    if not b:
        return redirect(url_for("index"))
    return render_template("confirmation.html", b=b)


# ---------- admin ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if (request.form.get("username") == ADMIN_USERNAME
                and request.form.get("password") == ADMIN_PASSWORD):
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        flash("Wrong username or password. Try again.", "danger")
    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("You are logged out.", "info")
    return redirect(url_for("admin_login"))


@app.route("/admin")
@admin_required
def admin_dashboard():
    d = db()
    s = d.execute("SELECT COUNT(*) t, SUM(status='available') f, SUM(status='booked') b FROM rooms").fetchone()
    bookings_count, revenue = d.execute("SELECT COUNT(*), COALESCE(SUM(total),0) FROM bookings").fetchone()
    recent = d.execute("SELECT b.*, r.room_number, r.room_type FROM bookings b "
                       "JOIN rooms r ON r.id=b.room_id ORDER BY b.id DESC LIMIT 5").fetchall()
    return render_template("admin_dashboard.html", total=s["t"], free=s["f"] or 0, busy=s["b"] or 0,
                           bookings_count=bookings_count, revenue=revenue, recent=recent)


@app.route("/admin/rooms")
@admin_required
def admin_rooms():
    rooms = db().execute("SELECT * FROM rooms ORDER BY room_number").fetchall()
    return render_template("admin_rooms.html", rooms=rooms)


@app.route("/admin/rooms/add", methods=["GET", "POST"])
@admin_required
def add_room():
    if request.method == "POST":
        try:
            price = float(request.form["price"])
            if price <= 0:
                raise ValueError
            db().execute("INSERT INTO rooms (room_number, room_type, price, status) VALUES (?,?,?,?)",
                         (request.form["number"].strip(), request.form["rtype"], price,
                          request.form.get("status", "available")))
            db().commit()
            flash("Room added.", "success")
            return redirect(url_for("admin_rooms"))
        except sqlite3.IntegrityError:
            flash("A room with that number already exists.", "danger")
        except ValueError:
            flash("Enter a price greater than zero.", "danger")
    return render_template("add_room.html", types=list(AMENITIES))


@app.route("/admin/rooms/<int:room_id>/delete", methods=["POST"])
@admin_required
def delete_room(room_id):
    d = db()
    room = d.execute("SELECT * FROM rooms WHERE id=?", (room_id,)).fetchone()
    if room and room["status"] == "available":
        d.execute("DELETE FROM rooms WHERE id=?", (room_id,))
        d.commit()
        flash("Room {} deleted.".format(room["room_number"]), "success")
    else:
        flash("Check out the guest before deleting this room.", "warning")
    return redirect(url_for("admin_rooms"))


@app.route("/admin/bookings")
@admin_required
def admin_bookings():
    bookings = db().execute("SELECT b.*, r.room_number, r.room_type FROM bookings b "
                            "JOIN rooms r ON r.id=b.room_id ORDER BY b.id DESC").fetchall()
    return render_template("admin_bookings.html", bookings=bookings)


@app.route("/admin/bookings/<int:booking_id>/checkout", methods=["POST"])
@admin_required
def checkout_booking(booking_id):
    d = db()
    b = d.execute("SELECT * FROM bookings WHERE id=?", (booking_id,)).fetchone()
    if b and b["status"] == "active":
        d.execute("UPDATE bookings SET status='checked_out' WHERE id=?", (booking_id,))
        d.execute("UPDATE rooms SET status='available' WHERE id=?", (b["room_id"],))
        d.commit()
        flash("{} checked out. The room is available again.".format(b["customer_name"]), "success")
    return redirect(url_for("admin_bookings"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
