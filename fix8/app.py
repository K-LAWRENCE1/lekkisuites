# Lekki Suites - Hotel Website
# This is the main Flask application file.
# Flask is a lightweight web framework that lets us serve web pages.

import json
import os
import sqlite3
import smtplib
from email.message import EmailMessage
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response

# Create the Flask application
app = Flask(__name__)
app.secret_key = "lekkisuites-secret-2026"


# --- Database helper ---
# We store every booking and food order in a small SQLite database file (bookings.db).
DB_NAME = "bookings.db"


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
        msg["From"] = "Lekki Suites <{}>".format(SMTP_USER)
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


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # lets us access columns by name
    return conn


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
    cols = {row[1] for row in conn.execute("PRAGMA table_info(bookings)").fetchall()}
    if "ticket_id" not in cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN ticket_id TEXT")
    if "status" not in cols:
        conn.execute("ALTER TABLE bookings ADD COLUMN status TEXT DEFAULT 'Pending'")

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
        conn.close()
        if b:
            cls, label = ticket_display(b)
            return render_template("ticket.html", b=b, status_class=cls, status_label=label)
        flash("No booking found for that ticket number.", "error")
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

    # Optional search (by name or ticket number).
    q = request.args.get("q", "").strip().lower()

    conn = get_db()
    bookings = conn.execute("SELECT * FROM bookings ORDER BY id DESC").fetchall()
    food_orders = conn.execute("SELECT * FROM food_orders ORDER BY id DESC").fetchall()
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
    return render_template("admin.html", rows=rows, stats=stats, q=request.args.get("q", ""),
                           new_orders_count=new_orders_count)


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
    return redirect(url_for("admin"))


# ===== ADMIN: FOOD ORDERS =====

@app.route("/admin/orders")
def admin_orders():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))

    conn = get_db()
    orders = conn.execute("SELECT * FROM food_orders ORDER BY id DESC").fetchall()
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
    return redirect(url_for("admin", _anchor="food-orders"))


# Change the status of a food order (New -> Preparing -> Ready -> Delivered).
@app.route("/admin/orders/status/<int:order_id>", methods=["POST"])
def admin_order_status(order_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin"))
    status = request.form.get("status", "")
    if status not in ("Preparing", "Ready", "Delivered"):
        return redirect(url_for("admin", _anchor="food-orders"))
    conn = get_db()
    conn.execute("UPDATE food_orders SET order_status = ? WHERE id = ?", (status, order_id))
    conn.commit()
    conn.close()
    return redirect(url_for("admin", _anchor="food-orders"))


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("admin"))


# This lets us run the website by typing:  python app.py
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)