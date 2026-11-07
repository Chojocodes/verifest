
"""
VeriFest — Dynamic QR Ticketing for College Fests
---------------------------------------------------
Differentiator vs. a plain "static QR ticket" system:

  1. ROTATING QR TOKENS. The QR code on a student's ticket changes every
     15 seconds (TOTP-style, like a bank's 2FA code). A screenshot shared
     with a friend goes stale within seconds — it isn't just "one-time
     use after first scan," it's unusable almost immediately even before
     anyone scans it. This is the core anti-screenshot-sharing feature
     most simple QR-ticket builds don't have.
  2. LIVE CAMERA GATE SCANNER with an AJAX result panel (no page reloads),
     so it's demoable on a judge's laptop camera in real time.
  3. Admin analytics dashboard (revenue, discount-tier mix, entries so far)
     for the "business value" angle judges look for.

Run: python app.py   (see README.md)
"""

import io
import os
import time
import sqlite3
import uuid
import hashlib
import hmac
from datetime import datetime

import qrcode
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, send_file, abort, jsonify
)

APP_SECRET = os.environ.get("APP_SECRET", "dev-secret-change-me")
TICKET_BASE_PRICE = 500  # INR
TOKEN_WINDOW_SECONDS = 15
DB_PATH = os.path.join(os.path.dirname(__file__), "verifest.db")

app = Flask(__name__)
app.secret_key = APP_SECRET


# ---------------------------------------------------------------- DB setup
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            ticket_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            roll_no TEXT NOT NULL,
            cgpa REAL NOT NULL,
            discount_pct INTEGER NOT NULL,
            final_price REAL NOT NULL,
            paid INTEGER DEFAULT 0,
            payment_ref TEXT,
            used INTEGER DEFAULT 0,
            used_at TEXT,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_email_unique ON tickets(email)
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS scan_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT,
            result TEXT,
            detail TEXT,
            at TEXT
        )
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------- business logic
def calculate_discount(cgpa: float) -> int:
    """Fair, deterministic, tiered discount allocation."""
    if cgpa > 9.5:
        return 20
    if cgpa > 9.0:
        return 15
    if cgpa > 8.5:
        return 10
    return 0


def current_window() -> int:
    return int(time.time() // TOKEN_WINDOW_SECONDS)


def token_for(ticket_id: str, window: int) -> str:
    """Rotating token: changes every TOKEN_WINDOW_SECONDS, just like a
    bank OTP. This is what makes the QR unusable moments after it's
    screenshotted, rather than only after its first scan."""
    msg = f"{ticket_id}:{window}"
    return hmac.new(APP_SECRET.encode(), msg.encode(), hashlib.sha256).hexdigest()[:10]


def make_qr_payload(ticket_id: str) -> str:
    w = current_window()
    return f"{ticket_id}:{w}:{token_for(ticket_id, w)}"


def log_scan(ticket_id, result, detail):
    conn = get_db()
    conn.execute(
        "INSERT INTO scan_attempts (ticket_id, result, detail, at) VALUES (?,?,?,?)",
        (ticket_id, result, detail, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


# --------------------------------------------------------------- routes
@app.route("/", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        roll_no = request.form["roll_no"].strip()
        try:
            cgpa = float(request.form["cgpa"])
        except ValueError:
            flash("Enter a valid CGPA.")
            return redirect(url_for("register"))

        if not (0 <= cgpa <= 10):
            flash("CGPA must be between 0 and 10.")
            return redirect(url_for("register"))

        discount = calculate_discount(cgpa)
        final_price = round(TICKET_BASE_PRICE * (1 - discount / 100), 2)
        ticket_id = str(uuid.uuid4())

        conn = get_db()
        try:
            conn.execute(
                """INSERT INTO tickets
                   (ticket_id, name, email, roll_no, cgpa, discount_pct,
                    final_price, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (ticket_id, name, email, roll_no, cgpa, discount,
                 final_price, datetime.utcnow().isoformat()),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            flash("This email has already registered for the fest. "
                  "One ticket per student (fraud prevention).")
            return redirect(url_for("register"))
        finally:
            conn.close()

        return redirect(url_for("pay", ticket_id=ticket_id))

    return render_template("register.html", base_price=TICKET_BASE_PRICE)


@app.route("/pay/<ticket_id>", methods=["GET", "POST"])
def pay(ticket_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
    if not row:
        conn.close()
        abort(404)

    if request.method == "POST":
        # MOCK payment gateway — in production, create an order with
        # Razorpay/Stripe, redirect to their hosted checkout, and only
        # flip paid=1 inside a server-side webhook after verifying the
        # gateway's signature. Never trust a client "payment done" ping.
        payment_ref = f"MOCKPAY-{uuid.uuid4().hex[:10].upper()}"
        conn.execute(
            "UPDATE tickets SET paid=1, payment_ref=? WHERE ticket_id=?",
            (payment_ref, ticket_id),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("ticket", ticket_id=ticket_id))

    conn.close()
    return render_template("payment.html", t=row)


@app.route("/ticket/<ticket_id>")
def ticket(ticket_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
    conn.close()
    if not row or not row["paid"]:
        abort(404)
    return render_template("ticket.html", t=row, window_seconds=TOKEN_WINDOW_SECONDS)


@app.route("/ticket/<ticket_id>/qr.png")
def ticket_qr(ticket_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
    conn.close()
    if not row or not row["paid"]:
        abort(404)

    img = qrcode.make(make_qr_payload(ticket_id))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    resp = send_file(buf, mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


# -------------------------------------------------- gate / entry scanning
@app.route("/scan")
def scan():
    return render_template("scan.html")


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """AJAX endpoint used by both the camera scanner and the manual-paste
    fallback on /scan. Validates: signature, time window (current or one
    window of grace), paid status, and single-use."""
    payload = (request.json or {}).get("payload", "").strip() if request.is_json else request.form.get("payload", "").strip()
    parts = payload.split(":")
    if len(parts) != 3:
        return jsonify(status="error", message="Malformed QR payload."), 400

    ticket_id, window_str, sig = parts
    try:
        window = int(window_str)
    except ValueError:
        return jsonify(status="error", message="Malformed QR payload."), 400

    now_w = current_window()
    valid_sig = any(
        hmac.compare_digest(sig, token_for(ticket_id, w))
        for w in (window, now_w, now_w - 1)
    ) and abs(now_w - window) <= 1

    if not valid_sig:
        log_scan(ticket_id, "denied", "expired or forged token")
        return jsonify(status="error", message="QR expired or invalid. Ask the student to refresh their ticket page. Entry denied."), 403

    conn = get_db()
    row = conn.execute("SELECT * FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
    if not row or not row["paid"]:
        conn.close()
        log_scan(ticket_id, "denied", "not found / unpaid")
        return jsonify(status="error", message="Ticket not found or unpaid. Entry denied."), 404

    if row["used"]:
        conn.close()
        log_scan(ticket_id, "denied", f"already used at {row['used_at']}")
        return jsonify(status="error", message=f"Already used at {row['used_at']}. Duplicate/shared QR suspected. Entry denied."), 409

    conn.execute(
        "UPDATE tickets SET used=1, used_at=? WHERE ticket_id=?",
        (datetime.utcnow().isoformat(), ticket_id),
    )
    conn.commit()
    conn.close()
    log_scan(ticket_id, "admitted", "ok")
    return jsonify(status="ok", message=f"Entry granted: {row['name']} ({row['roll_no']})")


# -------------------------------------------------------------- dashboard
@app.route("/admin")
def admin():
    conn = get_db()
    tickets = conn.execute("SELECT * FROM tickets ORDER BY created_at DESC").fetchall()
    revenue = sum(t["final_price"] for t in tickets if t["paid"])
    admitted = sum(1 for t in tickets if t["used"])
    paid_count = sum(1 for t in tickets if t["paid"])
    tier_counts = {0: 0, 10: 0, 15: 0, 20: 0}
    for t in tickets:
        tier_counts[t["discount_pct"]] = tier_counts.get(t["discount_pct"], 0) + 1
    recent_scans = conn.execute(
        "SELECT * FROM scan_attempts ORDER BY id DESC LIMIT 15"
    ).fetchall()
    conn.close()
    return render_template(
        "admin.html",
        tickets=tickets,
        revenue=revenue,
        admitted=admitted,
        paid_count=paid_count,
        tier_counts=tier_counts,
        recent_scans=recent_scans,
    )


if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=5000)
