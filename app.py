# Lekki Suites - Hotel Website
# This is the main Flask application file.
# Flask is a lightweight web framework that lets us serve web pages.

import sqlite3
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, session, flash

# Create the Flask application
app = Flask(__name__)
app.secret_key = "lekkisuites-secret-2026"


# --- Database helper ---
# We store every booking in a small SQLite database file (bookings.db).
DB_NAME = "bookings.db"


# --- Payment details shown to guests on the confirmation page ---
PAYMENT = {
    "bank": "Moniepoint",
    "account_name": "ONE LS HOTELS NIGERIA LIMITED - CHARLES NNAMDI JUNIOR EMODI",
    "account_number": "5870568143",
    "whatsapp": "2348092299428",
}

# --- Room prices (per night), used to estimate revenue ---
ROOM_PRICES = {
    "Standard Room": 25000,
    "Deluxe Room": 45000,
    "Executive Suite": 80000,
}


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # lets us access columns by name
    return conn


def init_db():
    """Create the bookings table if it does not exist, and upgrade old ones."""
    conn = get_db()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT NOT NULL,
            email TEXT,
            room_type TEXT NOT NULL,
            check_in TEXT NOT NULL,
            check_out TEXT NOT NULL,
            guests INTEGER NOT NULL,
            requests TEXT,
            booked_at TEXT NOT NULL,
            ticket_id TEXT,
            status TEXT DEFAULT 'Pending'
        )
        """
    )
    # Upgrade older databases: add new columns if they are missing.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(bookings)").fetchall()}
    if "ticket_id" not in cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN ticket_id TEXT")
    if "status" not in cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN status TEXT DEFAULT 'Pending'")
    conn.commit()
    conn.close()


# Create / upgrade the table once when the app starts.
init_db()


def ticket_display(b):
    """Work out how a ticket should look to a guest or the reception.

    Returns (css_class, label):
      - pending  -> booked but not paid yet
      - upcoming -> paid, but check-in date has not arrived
      - active   -> paid and currently within the stay dates
      - expired  -> the check-out date has passed
    """
    status = b["status"] if b["status"] else "Pending"
    if status != "Confirmed":
        return ("pending", "Pending Payment")
    try:
        today = date.today()
        ci = date.fromisoformat(b["check_in"])
        co = date.fromisoformat(b["check_out"])
    except (ValueError, TypeError):
        return ("confirmed", "Confirmed")
    if today > co:
        return ("expired", "Expired")
    if today < ci:
        return ("upcoming", "Confirmed")
    return ("active", "Valid")


# The route "/" is the home page of the website.
@app.route("/")
def home():
    return render_template("index.html")


# Rooms page - shows the rooms & suites.
@app.route("/rooms")
def rooms():
    return render_template("rooms.html")


# Amenities page - shows the hotel amenities.
@app.route("/amenities")
def amenities():
    return render_template("amenities.html")


# Dining page - shows the restaurant & bar info.
@app.route("/dining")
def dining():
    return render_template("dining.html")


# Contact page - shows address, phone, email and map.
@app.route("/contact")
def contact():
    return render_template("contact.html")


# ===== BOOKING SYSTEM =====

# Booking form page.
@app.route("/book", methods=["GET", "POST"])
def book():
    if request.method == "POST":
        # Collect the data the guest typed in the form.
        name = request.form.get("name", "").strip()
        phone = request.form.get("phone", "").strip()
        email = request.form.get("email", "").strip()
        room_type = request.form.get("room_type", "").strip()
        check_in = request.form.get("check_in", "").strip()
        check_out = request.form.get("check_out", "").strip()
        guests = request.form.get("guests", "1").strip()
        special = request.form.get("requests", "").strip()

        # Make sure the important fields are filled.
        if not name or not phone or not room_type or not check_in or not check_out:
            flash("Please fill in your name, phone, room type and dates.", "error")
            return render_template("book.html", form=request.form, preselect="")

        # Save the booking into the database.
        conn = get_db()
        cur = conn.execute(
            """
            INSERT INTO bookings
                (name, phone, email, room_type, check_in, check_out, guests, requests, booked_at, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
            """,
            (
                name,
                phone,
                email,
                room_type,
                check_in,
                check_out,
                int(guests) if guests.isdigit() else 1,
                special,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            ),
        )
        booking_id = cur.lastrowid
        # Generate a unique ticket number, e.g. LK-0001
        ticket_id = "LK-{:04d}".format(booking_id)
        conn.execute("UPDATE bookings SET ticket_id = ? WHERE id = ?", (ticket_id, booking_id))
        conn.commit()
        conn.close()

        # Send the guest to the confirmation page with their ticket + payment details.
        return render_template(
            "booking_success.html",
            name=name,
            room_type=room_type,
            check_in=check_in,
            check_out=check_out,
            guests=guests,
            phone=phone,
            ticket_id=ticket_id,
            payment=PAYMENT,
        )

    # GET request - just show the empty form.
    # If they clicked "Book Now" on a room, pre-select that room.
    preselect = request.args.get("room", "")
    return render_template("book.html", form=None, preselect=preselect)


# ===== CHECK TICKET (guest or reception verifies a booking) =====
@app.route("/ticket", methods=["GET", "POST"])
def ticket():
    ref = ""
    if request.method == "POST":
        ref = request.form.get("ref", "").strip().upper()
    else:
        ref = request.args.get("ref", "").strip().upper()

    if ref:
        conn = get_db()
        b = conn.execute("SELECT * FROM bookings WHERE UPPER(ticket_id) = ?", (ref,)).fetchone()
        conn.close()
        if b:
            cls, label = ticket_display(b)
            return render_template("ticket.html", b=b, status_class=cls, status_label=label)
        flash("No booking found for that ticket number.", "error")
        return redirect(url_for("ticket"))

    # No ticket number entered yet - show the search form.
    return render_template("ticket.html", b=None)


# ===== ADMIN PAGE (view all bookings) =====
# Password protected so only hotel staff can see the bookings.
ADMIN_PASSWORD = "lekkisuites2026"


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        # Login: check the password.
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        flash("Wrong password. Try again.", "error")
        return redirect(url_for("admin"))

    # If not logged in, show the login form.
    if not session.get("admin_logged_in"):
        return render_template("admin_login.html")

    # Optional search (by name or ticket number).
    q = request.args.get("q", "").strip().lower()

    conn = get_db()
    bookings = conn.execute("SELECT * FROM bookings ORDER BY id DESC").fetchall()
    conn.close()

    # --- Compute dashboard stats ---
    today = date.today()
    total = len(bookings)
    pending = confirmed = active = upcoming = expired = 0
    revenue = 0
    for b in bookings:
        cls, label = ticket_display(b)
        if cls == "pending":
            pending += 1
        elif cls == "active":
            active += 1
            confirmed += 1
        elif cls == "upcoming":
            upcoming += 1
            confirmed += 1
        elif cls == "expired":
            expired += 1
            confirmed += 1
        # Revenue from paid (Confirmed) bookings.
        if b["status"] == "Confirmed":
            try:
                nights = (date.fromisoformat(b["check_out"]) - date.fromisoformat(b["check_in"])).days
            except (ValueError, TypeError):
                nights = 0
            revenue += ROOM_PRICES.get(b["room_type"], 0) * max(nights, 0)

    # --- Filter rows by the search query ---
    rows = []
    for b in bookings:
        if q and q not in (b["name"] or "").lower() and q not in (b["ticket_id"] or "").lower():
            continue
        cls, label = ticket_display(b)
        rows.append((b, cls, label))

    stats = {
        "total": total,
        "pending": pending,
        "confirmed": confirmed,
        "active": active,
        "upcoming": upcoming,
        "expired": expired,
        "revenue": revenue,
    }
    return render_template("admin.html", rows=rows, stats=stats, q=request.args.get("q", ""))


# Mark a booking as paid / confirmed.
@app.route("/admin/confirm/<int:booking_id>", methods=["POST"])
def admin_confirm(booking_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))
    conn = get_db()
    conn.execute("UPDATE bookings SET status = 'Confirmed' WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin"))


# This lets us run the website by typing:  python app.py
if __name__ == "__main__":
    app.run(debug=True)
