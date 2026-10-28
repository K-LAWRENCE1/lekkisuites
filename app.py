# Lekki Suites - Hotel Website
# This is the main Flask application file.
# Flask is a lightweight web framework that lets us serve web pages.

import csv
import io
import json
import os
import smtplib
from email.message import EmailMessage
from datetime import datetime, date
from flask import (Flask, render_template, request, redirect, url_for, session, flash,
                   Response, send_from_directory, make_response)

# Create the Flask application
app = Flask(__name__)
app.secret_key = "lekkisuites-secret-2026"


# --- Database helper ---
# db.py decides where data lives: the bookings.db file locally, or Postgres on Render
# (it switches automatically as soon as a DATABASE_URL environment variable exists).
from db import get_db


# --- Payment details shown to guests on the confirmation page ---
PAYMENT = {
    "bank": "Moniepoint",
    "account_name": "ONE LS HOTELS NIGERIA LIMITED - CHARLES NNAMDI JUNIOR EMODI",
    "account_number": "5870568143",
    "whatsapp": "2348092299428",
}

# --- Email notifications (fix28) ---
# Set these in Render > Environment: SMTP_USER, SMTP_PASS, HOTEL_EMAIL
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
HOTEL_EMAIL = os.environ.get("HOTEL_EMAIL", "")
# The address guests actually see in the "From:" line. With Brevo the SMTP login
# (something@smtp-brevo.com) is NOT a real mailbox, so it must not be used here.
EMAIL_FROM = os.environ.get("EMAIL_FROM", "") or HOTEL_EMAIL or SMTP_USER

# --- Contact details used across the site (fix39) ---
# The footer/contact page now show these as tap-to-call / tap-to-mail links.
# They follow the HOTEL_EMAIL env var, so when the reservations@ mailbox exists
# you change one value in Render and every page updates by itself.
HOTEL_PHONE_DISPLAY = "+234 809 229 9428"
HOTEL_PHONE_TEL = "+2348092299428"
HOTEL_WHATSAPP = "2348092299428"


@app.context_processor
def inject_contact_details():
    return {
        "hotel_phone_display": HOTEL_PHONE_DISPLAY,
        "hotel_phone_tel": HOTEL_PHONE_TEL,
        "hotel_whatsapp": HOTEL_WHATSAPP,
        "hotel_email": HOTEL_EMAIL or "reservations@lekkisuites.com",
    }


def build_receipt(row, nights, amount):
    """Receipt text for a paid booking."""
    return (
        "PAYMENT RECEIVED - Lekki Suites\n\n"
        "Ticket:    {ticket}\n"
        "Name:      {name}\n"
        "Room:      {room}\n"
        "Check-in:  {check_in}\n"
        "Check-out: {check_out}\n"
        "Guests:    {guests}\n"
        "Nights:    {nights}\n"
        "Amount:    NGN {total:,}\n"
        "Status:    PAID\n\n"
        "Show this ticket at reception on arrival.\n"
        "1 Kayode Otitoju Street, Lekki Phase 1, Lagos\n"
        "Phone/WhatsApp: +234 809 229 9428\n"
        "https://lekkisuites.com/ticket"
    ).format(
        ticket=row["ticket_id"], name=row["name"], room=row["room_type"],
        check_in=row["check_in"], check_out=row["check_out"],
        guests=row["guests"], nights=nights, total=amount,
    )


def send_email(to_addr, subject, body):
    """Send one plain-text email. Never raises - returns True/False."""
    if not to_addr or not SMTP_USER or not SMTP_PASS:
        return False
    try:
        msg = EmailMessage()
        msg["From"] = "Lekki Suites <{}>".format(EMAIL_FROM)
        msg["Reply-To"] = EMAIL_FROM
        msg["To"] = to_addr
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as err:
        app.logger.warning("Email to %s failed: %s", to_addr, err)
        return False


# --- Room prices (per night), used to estimate revenue ---
ROOM_PRICES = {
    "Standard Room": 40000,
    "Executive Room": 45000,
    "Deluxe Room": 50000,
    "Deluxe Room (2 Beds)": 55000,
    "Executive Suite": 45000,
}


# ===== ROOM SERVICE MENU =====
# Every dish the kitchen serves, with prices in Naira.
# Each item gets a stable id so the cart can track it.
MENU = [
    {
        "section": "Rice Dishes",
        "category": "food",
        "dishes": [
            {"id": "jollof_turkey",   "name": "Jollof Rice & Turkey",      "price": 8000},
            {"id": "white_beef",      "name": "White Rice & Beef",          "price": 4000},
            {"id": "white_chicken",   "name": "White Rice & Chicken",       "price": 6000},
            {"id": "white_goat",      "name": "White Rice & Goat Meat",     "price": 6500},
            {"id": "white_turkey",     "name": "White Rice & Turkey",        "price": 8000},
        ],
    },
    {
        "section": "Pepper Soups",
        "category": "food",
        "dishes": [
            {"id": "ps_beef",     "name": "Beef Pepper Soup",      "price": 3000},
            {"id": "ps_chicken",  "name": "Chicken Pepper Soup",   "price": 5000},
            {"id": "ps_goat",     "name": "Goat Meat Pepper Soup", "price": 5500},
            {"id": "ps_assorted", "name": "Assorted Pepper Soup",  "price": 5000},
            {"id": "ps_turkey",   "name": "Turkey Pepper Soup",    "price": 7000},
        ],
    },
    {
        "section": "Pepper Soup & Yam",
        "category": "food",
        "dishes": [
            {"id": "psy_beef",     "name": "Beef Pepper Soup & Yam",       "price": 6000},
            {"id": "psy_chicken",  "name": "Chicken Pepper Soup & Yam",    "price": 8000},
            {"id": "psy_goat",     "name": "Goat Meat Pepper Soup & Yam",  "price": 8500},
            {"id": "psy_assorted", "name": "Assorted Pepper Soup & Yam",   "price": 8000},
            {"id": "psy_turkey",   "name": "Turkey Pepper Soup & Yam",     "price": 10000},
        ],
    },
    {
        "section": "Peppered Meat",
        "category": "food",
        "dishes": [
            {"id": "pm_beef",     "name": "Pepper Beef",        "price": 2000},
            {"id": "pm_chicken",  "name": "Pepper Chicken",    "price": 4000},
            {"id": "pm_goat",     "name": "Pepper Goat Meat",  "price": 4500},
            {"id": "pm_assorted", "name": "Pepper Assorted",   "price": 4000},
            {"id": "pm_turkey",   "name": "Pepper Turkey",     "price": 6000},
            {"id": "pm_yam",      "name": "Yam Pottage",         "price": 5000},
        ],
    },
    {
        "section": "Soups (served with Eba, Semo or Poundo)",
        "category": "food",
        "dishes": [
            {"id": "obg_beef",     "name": "Ogbono with Beef",                "price": 6000},
            {"id": "obg_chicken",  "name": "Ogbono with Chicken",             "price": 8000},
            {"id": "obg_goat",     "name": "Ogbono with Goat Meat / Assorted","price": 8500},
            {"id": "obg_turkey",   "name": "Ogbono with Turkey",              "price": 10000},
            {"id": "eg_beef",      "name": "Egusi with Beef",                  "price": 6000},
            {"id": "eg_chicken",   "name": "Egusi with Chicken",               "price": 8000},
            {"id": "eg_goat",      "name": "Egusi with Goat Meat / Assorted",  "price": 8500},
            {"id": "eg_turkey",    "name": "Egusi with Turkey",               "price": 10000},
            {"id": "af_beef",      "name": "Afang with Beef",                   "price": 6500},
            {"id": "af_chicken",   "name": "Afang with Chicken",                "price": 8500},
            {"id": "af_goat",      "name": "Afang with Goat Meat",              "price": 9000},
            {"id": "af_turkey",    "name": "Afang with Turkey",                 "price": 10500},
            {"id": "swallow_only", "name": "Eba / Semo / Poundo only",          "price": 1000},
        ],
    },
    {
        "section": "Water",
        "category": "bar",
        "dishes": [
            {"id": "w_table",  "name": "Table Water 75cl", "price": 500},
        ],
    },
    {
        "section": "Beer",
        "category": "bar",
        "dishes": [
            {"id": "b_heineken",  "name": "Heineken",       "price": 3000},
            {"id": "b_bigstout",  "name": "Big Stout",      "price": 3000},
            {"id": "b_bud",       "name": "Budweiser",      "price": 3000},
            {"id": "b_orijin",    "name": "Orijin Bitters", "price": 2500},
            {"id": "b_guilder",   "name": "Guilder",        "price": 2500},
            {"id": "b_goldberg",  "name": "Goldberg",       "price": 2000},
            {"id": "b_trophy",    "name": "Trophy",         "price": 2000},
            {"id": "b_smallstout","name": "Small Stout",    "price": 2000},
            {"id": "b_smirnoff",  "name": "Smirnoff Ice",   "price": 2000},
            {"id": "b_radler",    "name": "Star Radler",    "price": 2000},
            {"id": "b_desperado", "name": "Desperado",      "price": 2000},
            {"id": "b_star",      "name": "Star",           "price": 2000},
            {"id": "b_33",        "name": '"33"',           "price": 2000},
        ],
    },
    {
        "section": "Energy Drinks",
        "category": "bar",
        "dishes": [
            {"id": "e_monster", "name": "Monster", "price": 3000},
            {"id": "e_redbull", "name": "Redbull",  "price": 4000},
            {"id": "e_bullet",  "name": "Bullet",   "price": 3000},
        ],
    },
    {
        "section": "Juice",
        "category": "bar",
        "dishes": [
            {"id": "j_chivita",  "name": "Chivita",  "price": 4000},
            {"id": "j_exotic",   "name": "Exotic",   "price": 4000},
            {"id": "j_hollandia","name": "Hollandia","price": 4500},
        ],
    },
]

# Quick lookup: id -> item dict, so the cart can find items fast.
MENU_BY_ID = {}
for _section in MENU:
    for _item in _section["dishes"]:
        MENU_BY_ID[_item["id"]] = _item


def init_db():
    """Create the bookings + food_orders tables if they do not exist, and upgrade old ones."""
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
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(bookings)").fetchall()}
    if "ticket_id" not in cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN ticket_id TEXT")
    if "status" not in cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN status TEXT DEFAULT 'Pending'")
    if "notes" not in cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN notes TEXT")
    if "updated_at" not in cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN updated_at TEXT")
    if "room_no" not in cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN room_no TEXT")
    # fix40: deleting a booking now only HIDES it (deleted_at is set), so it can
    # be restored from the History page and its ticket number is never reused.
    if "deleted_at" not in cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN deleted_at TEXT")

    # --- Food orders table (room service) ---
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS food_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_ref TEXT NOT NULL,
            guest_name TEXT NOT NULL,
            room_number TEXT NOT NULL,
            phone TEXT,
            items TEXT NOT NULL,
            total INTEGER NOT NULL,
            payment_method TEXT NOT NULL,
            payment_status TEXT NOT NULL DEFAULT 'Pending',
            order_status TEXT NOT NULL DEFAULT 'New',
            created_at TEXT NOT NULL
        )
        """
    )
    order_cols = {row["name"] for row in conn.execute("PRAGMA table_info(food_orders)").fetchall()}
    if "deleted_at" not in order_cols:
        conn.execute("ALTER TABLE food_orders ADD COLUMN deleted_at TEXT")

    # --- Activity log table (history of everything) ---
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            logged_at TEXT NOT NULL,
            category TEXT NOT NULL,
            event TEXT NOT NULL,
            ref TEXT,
            detail TEXT
        )
        """
    )
    conn.commit()
    conn.close()


# Create / upgrade the tables once when the app starts.
init_db()


def log_activity(category, event, ref, detail):
    """Record an event in the activity log."""
    try:
        conn = get_db()
        conn.execute(
            "INSERT INTO activity_log (logged_at, category, event, ref, detail) VALUES (?, ?, ?, ?, ?)",
            (datetime.now().strftime("%Y-%m-%d %H:%M"), category, event, ref, detail),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def ticket_display(b):
    """Work out how a ticket should look to a guest or the reception.

    Returns (css_class, label):
      - pending  -> booked but not paid yet
      - upcoming -> paid, but check-in date has not arrived
      - active   -> paid and currently within the stay dates
      - expired  -> the check-out date has passed
    """
    status = b["status"] if b["status"] else "Pending"

    # Reception-only states that override the date-based ones (fix32).
    if status == "Cancelled":
        return ("cancelled", "Cancelled")
    if status == "No-show":
        return ("noshow", "No-show")
    if status == "Checked Out":
        return ("expired", "Checked Out")

    if status not in ("Confirmed", "Checked In"):
        return ("pending", "Pending Payment")
    if status == "Checked In":
        return ("active", "Checked In")
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


# ===== HELPERS FOR THE CART =====

def get_cart():
    """Return the current cart as a list of {id, name, price, qty}.

    Robust against stale or corrupt session data from older versions.
    """
    raw = session.get("cart", {})
    # If the session has bad data from an old version, wipe it.
    if not isinstance(raw, dict):
        session["cart"] = {}
        session.modified = True
        return []
    out = []
    for item_id, qty in raw.items():
        if not isinstance(item_id, str):
            continue
        try:
            qty = int(qty)
        except (ValueError, TypeError):
            continue
        if qty <= 0:
            continue
        item = MENU_BY_ID.get(item_id)
        if item:
            out.append({"id": item["id"], "name": item["name"], "price": item["price"], "qty": qty})
    return out


def get_cart_dict():
    """Safely get the raw cart dict from session, fixing bad data."""
    cart = session.get("cart", {})
    if not isinstance(cart, dict):
        cart = {}
        session["cart"] = cart
        session.modified = True
    return cart


def cart_total(cart=None):
    """Sum up the total naira value of the cart."""
    if cart is None:
        cart = get_cart()
    return sum(i["price"] * i["qty"] for i in cart)


# --- Guest reviews shown on the home page (fix32) ---
# Two knobs: the public Google rating, and real quotes once you have them.
# REVIEWS stays empty until you paste genuine guest words in here — nothing
# on this site invents a review.
#   {"name": "Ada O.", "text": "Quiet, clean and the staff were kind.", "when": "Oct 2026"}
GOOGLE_RATING = {
    "score": 3.9,
    "count": 238,
    "url": "https://www.google.com/search?q=Lekki+Suites+Lekki+Phase+1+Lagos+reviews",
}
REVIEWS = []


# The route "/" is the home page of the website.
@app.route("/")
def home():
    return render_template("index.html", rating=GOOGLE_RATING, reviews=REVIEWS)


# Rooms page - shows the rooms & suites.
@app.route("/rooms")
def rooms():
    return render_template("rooms.html")


# Amenities page - shows the hotel amenities.
@app.route("/amenities")
def amenities():
    return render_template("amenities.html")


# Dining page - now an interactive menu guests can order from.
@app.route("/dining")
def dining():
    cart = get_cart()
    return render_template("dining.html", menu=MENU, cart=cart, cart_total=cart_total(cart))


# Contact page - shows address, phone, email and map.
# ===== SEO: robots.txt + sitemap.xml (fix30) =====
SITE_URL = "https://lekkisuites.com"

@app.route("/robots.txt")
def robots_txt():
    body = "User-agent: *\nAllow: /\nDisallow: /admin\n\nSitemap: {}/sitemap.xml\n".format(SITE_URL)
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    pages = ["/", "/rooms", "/amenities", "/dining", "/contact", "/book", "/ticket"]
    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for page in pages:
        parts.append("<url><loc>{}{}</loc><changefreq>weekly</changefreq></url>".format(SITE_URL, page))
    parts.append("</urlset>")
    return Response("\n".join(parts), mimetype="application/xml")


# ===== PWA (fix36): manifest + service worker served from the site root =====
# A service worker only controls pages at or below its own folder, so /sw.js
# must live at "/" - that is why these two files are routed by hand instead of
# being served straight from /static/.
@app.route("/sw.js")
def service_worker():
    resp = make_response(send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript"))
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp


@app.route("/manifest.webmanifest")
def web_manifest():
    resp = make_response(send_from_directory(
        app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json"))
    resp.headers["Cache-Control"] = "public, max-age=3600"
    return resp


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
        log_activity("Booking", "New Booking", ticket_id,
                     "{} booked {} for {} to {} ({} guests)".format(name, room_type, check_in, check_out, guests))

        # Work out the number of nights and the total price, so the guest sees it on the ticket.
        try:
            nights = (date.fromisoformat(check_out) - date.fromisoformat(check_in)).days
        except ValueError:
            nights = 0
        nights = max(nights, 1) if nights > 0 else 0
        total_amount = ROOM_PRICES.get(room_type, 0) * nights

        # Email the guest, plus a copy to the hotel as a backup of the booking.
        message_body = (
            "Hello {name},\n\n"
            "Your booking at Lekki Suites is confirmed.\n\n"
            "Ticket:    {ticket}\n"
            "Room:      {room}\n"
            "Check-in:  {check_in}\n"
            "Check-out: {check_out}\n"
            "Guests:    {guests}\n"
            "Nights:    {nights}\n"
            "Total:     NGN {total:,}\n\n"
            "Address: 1 Kayode Otitoju Street, Lekki Phase 1, Lagos\n"
            "Phone/WhatsApp: +234 809 229 9428\n\n"
            "Check your booking any time at https://lekkisuites.com/ticket "
            "using ticket number {ticket}.\n\n"
            "Please pay at the hotel on arrival.\n\n"
            "Lekki Suites"
        ).format(
            name=name, ticket=ticket_id, room=room_type, check_in=check_in,
            check_out=check_out, guests=guests, nights=nights, total=total_amount,
        )
        send_email(email, "Booking {} confirmed - Lekki Suites".format(ticket_id), message_body)
        if HOTEL_EMAIL:
            send_email(HOTEL_EMAIL, "New booking {} - {}".format(ticket_id, name), message_body)

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
            nights=nights,
            total_amount=total_amount,
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
        # fix52: a room-service order can be checked too, using its ORD- number.
        o = None
        if not b:
            o = conn.execute(
                "SELECT * FROM food_orders WHERE UPPER(order_ref) = ? AND deleted_at IS NULL",
                (ref,),
            ).fetchone()
        conn.close()
        if b:
            cls, label = ticket_display(b)
            return render_template("ticket.html", b=b, status_class=cls, status_label=label)
        if o:
            # fix54: order items may be stored as {id: qty} or as a list of
            # entries, depending on which version created the order. Accept both.
            try:
                raw_items = json.loads(o["items"]) or {}
            except Exception:
                raw_items = {}
            pairs = []
            if isinstance(raw_items, dict):
                pairs = list(raw_items.items())
            elif isinstance(raw_items, list):
                for entry in raw_items:
                    if isinstance(entry, dict):
                        iid = entry.get("id") or entry.get("item_id") or entry.get("name")
                        qty = entry.get("qty") or entry.get("quantity") or 1
                        pairs.append((iid, qty))
                    elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                        pairs.append((entry[0], entry[1]))
                    elif isinstance(entry, str):
                        pairs.append((entry, 1))
            lines = []
            for item_id, qty in pairs:
                dish = MENU_BY_ID.get(item_id) if isinstance(item_id, str) else None
                if dish is None and isinstance(item_id, str):
                    for _d in MENU_BY_ID.values():
                        if _d["name"].lower() == item_id.lower():
                            dish = _d
                            break
                name = dish["name"] if dish else str(item_id)
                price = dish["price"] if dish else 0
                try:
                    qty = int(qty)
                except Exception:
                    qty = 1
                lines.append({"name": name, "qty": qty, "total": price * qty})
            return render_template("order_ticket.html", o=o, lines=lines)
        flash("No booking or order found for that number.", "error")
        return redirect(url_for("ticket"))

    # No ticket number entered yet - show the search form.
    return render_template("ticket.html", b=None)


# ===== ROOM SERVICE CART =====

# Add an item to the cart.
@app.route("/cart/add", methods=["POST"])
def cart_add():
    item_id = request.form.get("item_id", "")
    if item_id not in MENU_BY_ID:
        flash("That item is not on the menu.", "error")
        return redirect(url_for("dining"))

    cart = get_cart_dict()
    cart[item_id] = cart.get(item_id, 0) + 1
    session["cart"] = cart
    flash('"{}" added to your order.'.format(MENU_BY_ID[item_id]["name"]), "ok")
    return redirect(url_for("dining", _anchor="menu"))


# Remove one unit of an item from the cart.
@app.route("/cart/remove", methods=["POST"])
def cart_remove():
    item_id = request.form.get("item_id", "")
    cart = get_cart_dict()
    if item_id in cart:
        cart[item_id] -= 1
        if cart[item_id] <= 0:
            del cart[item_id]
        session["cart"] = cart
    return redirect(url_for("dining", _anchor="orderCart"))


# Delete an item from the cart entirely.
@app.route("/cart/delete", methods=["POST"])
def cart_delete():
    item_id = request.form.get("item_id", "")
    cart = get_cart_dict()
    cart.pop(item_id, None)
    session["cart"] = cart
    return redirect(url_for("dining", _anchor="orderCart"))


# Empty the whole cart.
@app.route("/cart/clear", methods=["POST"])
def cart_clear():
    session["cart"] = {}
    return redirect(url_for("dining", _anchor="menu"))


# ===== CHECKOUT (guest enters details + picks payment) =====

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart = get_cart()

    # If the cart is empty, send them back to the menu.
    if not cart:
        flash("Your order is empty. Add some items from the menu first.", "error")
        return redirect(url_for("dining"))

    if request.method == "POST":
        guest_name = request.form.get("guest_name", "").strip()
        room_number = request.form.get("room_number", "").strip()
        phone = request.form.get("phone", "").strip()
        payment_method = request.form.get("payment_method", "").strip()

        if not guest_name or not room_number or payment_method not in ("transfer", "cash"):
            flash("Please enter your name, room number and pick a payment method.", "error")
            return render_template("checkout.html", cart=cart, cart_total=cart_total(cart),
                                   form=request.form, payment=PAYMENT)

        total = cart_total(cart)
        # Save the items as JSON so we keep name + price + qty forever,
        # even if the menu changes later.
        items_json = json.dumps(cart, ensure_ascii=False)

        if payment_method == "transfer":
            pay_status = "Pending"
        else:
            pay_status = "Cash on Delivery"

        conn = get_db()
        cur = conn.execute(
            """
            INSERT INTO food_orders
                (order_ref, guest_name, room_number, phone, items, total,
                 payment_method, payment_status, order_status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'New', ?)
            """,
            (
                "",  # filled in after we know the id
                guest_name,
                room_number,
                phone,
                items_json,
                total,
                payment_method,
                pay_status,
                datetime.now().strftime("%Y-%m-%d %H:%M"),
            ),
        )
        order_id = cur.lastrowid
        order_ref = "ORD-{:04d}".format(order_id)
        conn.execute("UPDATE food_orders SET order_ref = ? WHERE id = ?", (order_ref, order_id))
        conn.commit()
        conn.close()
        log_activity("Food Order", "New Order", order_ref,
                     "{} in Room {} placed an order - {} ({} items, total {})".format(
                         guest_name, room_number, payment_method.title(),
                         len(cart), total))

        # Order placed -> empty the cart.
        session["cart"] = {}

        return render_template("order_success.html", order_ref=order_ref,
                               guest_name=guest_name, room_number=room_number,
                               phone=phone, cart=cart, total=total,
                               payment_method=payment_method, payment=PAYMENT)

    # GET - show the checkout form.
    return render_template("checkout.html", cart=cart, cart_total=cart_total(cart),
                           form=None, payment=PAYMENT)


# ===== ADMIN PAGE (view all bookings + food orders) =====
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

    # Optional search (name, ticket number, phone) and status filter.
    q = request.args.get("q", "").strip().lower()
    view = request.args.get("view", "all")  # all | today | pending | paid | closed

    conn = get_db()
    bookings = conn.execute(
        "SELECT * FROM bookings WHERE deleted_at IS NULL ORDER BY id DESC").fetchall()
    food_orders = conn.execute(
        "SELECT * FROM food_orders WHERE deleted_at IS NULL ORDER BY id DESC").fetchall()
    # fix42: how many deleted tickets/orders are sitting in History (badge on the History button).
    history_count = (
        conn.execute("SELECT COUNT(*) FROM bookings WHERE deleted_at IS NOT NULL").fetchone()[0]
        + conn.execute("SELECT COUNT(*) FROM food_orders WHERE deleted_at IS NOT NULL").fetchone()[0]
    )
    conn.close()

    # Count new food orders for the notification badge.
    new_orders_count = sum(1 for o in food_orders if o["order_status"] == "New")

    # --- Parse food orders so the history shows directly on this page ---
    parsed_orders = []
    for o in food_orders:
        try:
            items = json.loads(o["items"])
        except (ValueError, TypeError):
            items = []
        parsed_orders.append((o, items))

    # Food order stats
    o_new = sum(1 for o in food_orders if o["order_status"] == "New")
    o_prep = sum(1 for o in food_orders if o["order_status"] == "Preparing")
    o_ready = sum(1 for o in food_orders if o["order_status"] == "Ready")
    o_delivered = sum(1 for o in food_orders if o["order_status"] == "Delivered")
    food_revenue = sum(o["total"] for o in food_orders
                       if o["payment_status"] in ("Confirmed", "Cash on Delivery"))
    order_stats = {
        "total": len(food_orders),
        "new": o_new,
        "preparing": o_prep,
        "ready": o_ready,
        "delivered": o_delivered,
        "revenue": food_revenue,
    }

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

    # --- Today's arrivals: due to check in today, not yet cancelled ---
    today_str = today.isoformat()
    arrivals = [b for b in bookings
                if (b["check_in"] or "") == today_str
                and (b["status"] or "Pending") not in ("Cancelled", "No-show", "Checked Out")]
    departing = [b for b in bookings
                 if (b["check_out"] or "") == today_str
                 and (b["status"] or "") == "Checked In"]
    in_house = sum(1 for b in bookings if (b["status"] or "") == "Checked In")

    # --- Filter rows by search + the selected view tab ---
    def matches_view(b):
        st = b["status"] or "Pending"
        if view == "today":
            return (b["check_in"] or "") == today_str or st == "Checked In"
        if view == "pending":
            return st == "Pending"
        if view == "paid":
            return st in ("Confirmed", "Checked In")
        if view == "closed":
            return st in ("Checked Out", "Cancelled", "No-show")
        return True

    rows = []
    for b in bookings:
        if q and not (
            q in (b["name"] or "").lower()
            or q in (b["ticket_id"] or "").lower()
            or q in (b["phone"] or "").lower()
            or q in (b["room_no"] or "").lower()
        ):
            continue
        if not matches_view(b):
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
        "arrivals": len(arrivals),
        "in_house": in_house,
        "departing": len(departing),
    }
    return render_template("admin.html", rows=rows, stats=stats, q=request.args.get("q", ""),
                           view=view, arrivals=arrivals, departing=departing,
                           new_orders_count=new_orders_count,
                           history_count=history_count,
                           today_label=today.strftime("%a %d %b"))


# Mark a booking as paid / confirmed.
@app.route("/admin/confirm/<int:booking_id>", methods=["POST"])
def admin_confirm(booking_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))
    conn = get_db()
    b = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    conn.execute("UPDATE bookings SET status = 'Confirmed' WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()
    if b:
        try:
            nights = (date.fromisoformat(b["check_out"]) - date.fromisoformat(b["check_in"])).days
        except (ValueError, TypeError):
            nights = 0
        amount = ROOM_PRICES.get(b["room_type"], 0) * max(nights, 0)
        log_activity("Booking", "Payment Confirmed", b["ticket_id"],
                     "{} marked as Paid - {} ({} nights x {}) = {}".format(
                         b["name"], b["room_type"], nights, ROOM_PRICES.get(b["room_type"], 0), amount))

        # Email the receipt to the guest (only if they were not already marked paid).
        if b["status"] != "Confirmed":
            receipt = build_receipt(b, max(nights, 0), amount)
            if b["email"]:
                send_email(b["email"], "Payment received - Ticket {}".format(b["ticket_id"]), receipt)
            if HOTEL_EMAIL:
                send_email(HOTEL_EMAIL, "PAID {} - {}".format(b["ticket_id"], b["name"]), receipt)
    return back_to_admin()


# ===== ADMIN: RECEPTION ACTIONS (fix32) =====

# The whole point of a front desk is changing a booking's state as the guest
# moves through it. One endpoint handles every move so the templates stay simple.
BOOKING_ACTIONS = {
    "paid": ("Confirmed", "Marked as Paid"),
    "checkin": ("Checked In", "Checked In"),
    "checkout": ("Checked Out", "Checked Out"),
    "cancel": ("Cancelled", "Cancelled"),
    "noshow": ("No-show", "Marked No-show"),
    "reopen": ("Confirmed", "Reopened"),
}


@app.route("/admin/booking/<int:booking_id>/action", methods=["POST"])
def admin_booking_action(booking_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    action = request.form.get("action", "")
    if action not in BOOKING_ACTIONS:
        flash("Unknown action.", "error")
        return back_to_admin()

    new_status, label = BOOKING_ACTIONS[action]
    conn = get_db()
    b = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if not b:
        conn.close()
        return back_to_admin()

    conn.execute(
        "UPDATE bookings SET status = ?, updated_at = ? WHERE id = ?",
        (new_status, datetime.now().strftime("%Y-%m-%d %H:%M"), booking_id),
    )
    conn.commit()
    conn.close()

    log_activity("Booking", label, b["ticket_id"],
                 "{} - {} -> {}".format(b["name"], b["status"] or "Pending", new_status))

    # Marking paid still sends the receipt/confirmation emails.
    if action == "paid" and (b["status"] or "") != "Confirmed":
        try:
            nights = (date.fromisoformat(b["check_out"]) - date.fromisoformat(b["check_in"])).days
        except (ValueError, TypeError):
            nights = 0
        amount = ROOM_PRICES.get(b["room_type"], 0) * max(nights, 0)
        receipt = build_receipt(b, max(nights, 0), amount)
        if b["email"]:
            send_email(b["email"], "Payment received - Ticket {}".format(b["ticket_id"]), receipt)
        if HOTEL_EMAIL:
            send_email(HOTEL_EMAIL, "PAID {} - {}".format(b["ticket_id"], b["name"]), receipt)

    return back_to_admin()


@app.route("/admin/booking/<int:booking_id>/delete", methods=["POST"])
def admin_booking_delete(booking_id):
    """fix40: move a booking to History instead of erasing it.

    The row stays in the database, so the ticket number is never handed to
    another guest, and reception can restore it if someone deletes it by mistake.
    """
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    conn = get_db()
    b = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if not b:
        conn.close()
        return back_to_admin()

    conn.execute("UPDATE bookings SET deleted_at = ? WHERE id = ?",
                 (datetime.now().strftime("%Y-%m-%d %H:%M"), booking_id))
    conn.commit()
    conn.close()

    log_activity("Booking", "Deleted", b["ticket_id"],
                 "{} - {} ({}) - moved to History".format(b["name"], b["room_type"], b["check_in"]))
    flash("Ticket {} moved to History.".format(b["ticket_id"]), "success")
    return back_to_admin()


@app.route("/admin/booking/<int:booking_id>/restore", methods=["POST"])
def admin_booking_restore(booking_id):
    """fix40: bring a booking back out of History."""
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    conn = get_db()
    b = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
    if b:
        conn.execute("UPDATE bookings SET deleted_at = NULL WHERE id = ?", (booking_id,))
        conn.commit()
        log_activity("Booking", "Restored", b["ticket_id"], b["name"])
        flash("Ticket {} restored.".format(b["ticket_id"]), "success")
    conn.close()
    return back_to_admin("admin_history")


@app.route("/admin/orders/<int:order_id>/delete", methods=["POST"])
def admin_order_delete(order_id):
    """fix40: move a food order to History."""
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    conn = get_db()
    o = conn.execute("SELECT * FROM food_orders WHERE id = ?", (order_id,)).fetchone()
    if o:
        conn.execute("UPDATE food_orders SET deleted_at = ? WHERE id = ?",
                     (datetime.now().strftime("%Y-%m-%d %H:%M"), order_id))
        conn.commit()
        log_activity("Food", "Deleted", o["order_ref"], "{} - moved to History".format(o["guest_name"]))
        flash("Order {} moved to History.".format(o["order_ref"]), "success")
    conn.close()
    return back_to_admin("admin_orders")


@app.route("/admin/orders/<int:order_id>/restore", methods=["POST"])
def admin_order_restore(order_id):
    """fix40: bring a food order back out of History."""
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    conn = get_db()
    o = conn.execute("SELECT * FROM food_orders WHERE id = ?", (order_id,)).fetchone()
    if o:
        conn.execute("UPDATE food_orders SET deleted_at = NULL WHERE id = ?", (order_id,))
        conn.commit()
        log_activity("Food", "Restored", o["order_ref"], o["guest_name"])
        flash("Order {} restored.".format(o["order_ref"]), "success")
    conn.close()
    return back_to_admin("admin_history")


@app.route("/admin/history/booking/<int:booking_id>/purge", methods=["POST"])
def admin_booking_purge(booking_id):
    """fix51: throw a deleted ticket away for good (only reachable from History).

    The ticket number is still never reused - the sequence only moves forward.
    """
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    conn = get_db()
    b = conn.execute(
        "SELECT * FROM bookings WHERE id = ? AND deleted_at IS NOT NULL",
        (booking_id,)).fetchone()
    if b is None:
        conn.close()
        flash("That ticket is not in History.", "error")
        return back_to_admin("admin_history")

    conn.execute("DELETE FROM bookings WHERE id = ?", (booking_id,))
    conn.commit()
    conn.close()
    log_activity("Booking", "Purged", b["ticket_id"] or str(booking_id),
                 "{} - deleted from History for good".format(b["name"]))
    flash("Ticket {} deleted for good.".format(b["ticket_id"] or booking_id), "success")
    return back_to_admin("admin_history")


@app.route("/admin/history/order/<int:order_id>/purge", methods=["POST"])
def admin_order_purge(order_id):
    """fix51: throw a deleted food order away for good."""
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    conn = get_db()
    o = conn.execute(
        "SELECT * FROM food_orders WHERE id = ? AND deleted_at IS NOT NULL",
        (order_id,)).fetchone()
    if o is None:
        conn.close()
        flash("That order is not in History.", "error")
        return back_to_admin("admin_history")

    conn.execute("DELETE FROM food_orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    log_activity("Food", "Purged", o["order_ref"], "{} - deleted from History for good".format(o["guest_name"]))
    flash("Order {} deleted for good.".format(o["order_ref"]), "success")
    return back_to_admin("admin_history")


@app.route("/admin/history")
def admin_history():
    """fix40: everything that was deleted, with a Restore button."""
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    conn = get_db()
    bookings = conn.execute(
        "SELECT * FROM bookings WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC").fetchall()
    orders = conn.execute(
        "SELECT * FROM food_orders WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC").fetchall()
    conn.close()

    parsed_orders = []
    for o in orders:
        try:
            items = json.loads(o["items"])
        except (ValueError, TypeError):
            items = []
        parsed_orders.append((o, items))

    return render_template("admin_history.html", bookings=bookings, orders=parsed_orders,
                           new_orders_count=0)


@app.route("/admin/booking/<int:booking_id>/update", methods=["POST"])
def admin_booking_update(booking_id):
    """Save the reception notes and the physical room number for a booking."""
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    notes = (request.form.get("notes") or "").strip()[:1000]
    room_no = (request.form.get("room_no") or "").strip()[:20]

    conn = get_db()
    conn.execute(
        "UPDATE bookings SET notes = ?, room_no = ?, updated_at = ? WHERE id = ?",
        (notes, room_no, datetime.now().strftime("%Y-%m-%d %H:%M"), booking_id),
    )
    conn.commit()
    conn.close()
    log_activity("Booking", "Notes Updated", str(booking_id), notes[:120] or room_no)
    return back_to_admin()


@app.route("/admin/bookings.csv")
def admin_bookings_csv():
    """Download every booking as a spreadsheet file (backup before a redeploy)."""
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    conn = get_db()
    bookings = conn.execute("SELECT * FROM bookings ORDER BY id DESC").fetchall()
    conn.close()

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Ticket", "Name", "Phone", "Email", "Room Type", "Room No",
                     "Check-in", "Check-out", "Nights", "Guests", "Status",
                     "Amount (NGN)", "Booked At", "Notes"])
    for b in bookings:
        try:
            nights = (date.fromisoformat(b["check_out"]) - date.fromisoformat(b["check_in"])).days
        except (ValueError, TypeError):
            nights = 0
        amount = ROOM_PRICES.get(b["room_type"], 0) * max(nights, 0) if b["status"] != "Pending" else 0
        writer.writerow([
            b["ticket_id"], b["name"], b["phone"], b["email"], b["room_type"],
            b["room_no"], b["check_in"], b["check_out"], max(nights, 0), b["guests"],
            b["status"] or "Pending", amount, b["booked_at"], b["notes"],
        ])

    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=lekkisuites-bookings-{}.csv".format(stamp)},
    )


# ===== ADMIN: FOOD ORDERS =====

@app.route("/admin/orders")
def admin_orders():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    conn = get_db()
    orders = conn.execute(
        "SELECT * FROM food_orders WHERE deleted_at IS NULL ORDER BY id DESC").fetchall()
    conn.close()

    # Count new orders for the notification badge.
    new_count = sum(1 for o in orders if o["order_status"] == "New")
    preparing_count = sum(1 for o in orders if o["order_status"] == "Preparing")
    ready_count = sum(1 for o in orders if o["order_status"] == "Ready")
    delivered_count = sum(1 for o in orders if o["order_status"] == "Delivered")
    food_revenue = sum(o["total"] for o in orders if o["payment_status"] in ("Confirmed", "Cash on Delivery"))

    order_stats = {
        "total": len(orders),
        "new": new_count,
        "preparing": preparing_count,
        "ready": ready_count,
        "delivered": delivered_count,
        "revenue": food_revenue,
    }

    parsed = []
    for o in orders:
        try:
            items = json.loads(o["items"])
        except (ValueError, TypeError):
            items = []
        parsed.append((o, items))

    return render_template("admin_orders.html", orders=parsed, new_count=new_count,
                           order_stats=order_stats)


# Confirm a transfer payment for a food order.
@app.route("/admin/orders/confirm/<int:order_id>", methods=["POST"])
def admin_confirm_payment(order_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))
    conn = get_db()
    conn.execute("UPDATE food_orders SET payment_status = 'Confirmed' WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    return back_to_admin()


# Change the status of a food order (New -> Preparing -> Ready -> Delivered).
@app.route("/admin/orders/status/<int:order_id>", methods=["POST"])
def admin_order_status(order_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))
    status = request.form.get("status", "")
    if status not in ("Preparing", "Ready", "Delivered"):
        return back_to_admin()
    conn = get_db()
    conn.execute("UPDATE food_orders SET order_status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()
    return back_to_admin()


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return back_to_admin()


def back_to_admin(default_endpoint="admin", **kwargs):
    """fix50: send staff back to the exact page they acted from.

    Using the referring page keeps the tab (?view=), the search (?q=) and the
    anchor intact instead of dumping them back at the top of the bookings list.
    """
    ref = request.referrer or ""
    if ref.startswith(request.host_url):
        return redirect(ref)
    return redirect(url_for(default_endpoint, **kwargs))

# --- fix48: temporary diagnostic -------------------------------------------
# While we hunt a 500 on /admin, a logged-in staff member sees the real error
# instead of Render's blank "Internal Server Error" page. Remove once fixed.
from werkzeug.exceptions import HTTPException


@app.errorhandler(Exception)
def _admin_diagnostic(error):
    if isinstance(error, HTTPException):
        return error
    # fix55: errors are logged for the Render log, never shown to visitors.
    app.logger.error("500 on %s: %s", request.path, error, exc_info=True)
    if not (request.path.startswith("/admin") and session.get("admin_logged_in")):
        return "Internal Server Error", 500
    import traceback
    tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
    return ("<pre style=\"padding:16px;font-size:12px;white-space:pre-wrap;"
            "font-family:monospace;background:#fff;color:#111\">"
            + tb.replace("&", "&amp;").replace("<", "&lt;") + "</pre>"), 500


# This lets us run the website by typing:  python app.py
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)