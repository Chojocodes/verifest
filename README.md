# VeriFest — Dynamic QR Ticketing for College Fests

Built for the Samvitya problem statement: *Smart College Fest Ticketing System*.

## What makes this different (say this out loud in your pitch)

Most quick solutions to this problem statement converge on the same idea:
CGPA discount + a static QR ticket that's invalidated after first scan.
VeriFest does that too, but adds three things a judge will notice:

1. **Rotating QR tokens, not a static one.** The ticket's QR code changes
   every 15 seconds — like a bank's OTP — using an HMAC token keyed to a
   15-second time window. A static QR only stops a *second* use; a
   screenshot of it is still perfectly usable until someone scans it
   first. A rotating QR is unusable within seconds of being screenshotted,
   even if nobody has scanned it yet. This is a materially stronger
   anti-duplication guarantee, and it's easy to explain on a poster with
   one diagram (ticket_id + time_window + secret → token).
2. **A live camera scanner, not a paste box.** `/scan` uses your device
   camera to decode the QR in real time and shows a pass/fail panel
   instantly — this is what makes the project *demoable* in front of
   judges instead of just describable.
3. **An organizer dashboard** (`/admin`) with revenue, discount-tier mix,
   and check-in stats — because a ticketing system that only ticket-sells
   but gives organizers no visibility isn't really "complete."

## How it meets each requirement in the problem statement

| Requirement | Implementation |
|---|---|
| Fair discount allocation | `calculate_discount()` — fixed CGPA tiers (>9.5→20%, >9.0→15%, >8.5→10%), same rule for everyone. |
| Secure payment processing | Payment step isolated behind a clearly-marked mock gateway; comments in `app.py` show exactly where to plug in Razorpay/Stripe with server-side webhook signature verification. |
| Prevention of fraudulent registrations | One ticket per email (DB-enforced); rotating-token QR means stolen/forwarded screenshots fail within 15 seconds. |
| Strict entry authentication | `/scan` validates signature + time window + paid + unused, atomically, before marking a ticket used. |
| No ticket duplication | `used` flag flips exactly once per ticket; every attempt (admit or deny) is logged to `scan_attempts` for audit. |

## Run it locally

```bash
cd verifest
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

- Register + pay: http://localhost:5000
- Gate scanner (use on your phone or a second device/tab): http://localhost:5000/scan
- Organizer dashboard: http://localhost:5000/admin

For the live demo: open the ticket on one device, open `/scan` on another,
and scan — then try scanning the *same* QR again to show the duplicate
rejection, and wait 15s to show the token expiring.

## Push to GitHub

```bash
cd verifest
git init
git add .
git commit -m "VeriFest — dynamic QR ticketing"
git branch -M main
git remote add origin https://github.com/<your-username>/<repo-name>.git
git push -u origin main
```

## Deploy a live link (free)

**Render.com:**
1. Push to GitHub (above).
2. New → Web Service → connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Add environment variable `APP_SECRET` = any random string.
6. Deploy → you get `https://yourapp.onrender.com`.

Railway.app or PythonAnywhere work the same way.

## Honest limitations (mention these — it reads as rigor, not weakness)

- Payment is mocked for the demo; production needs a real gateway with
  server-side signature verification, not a client-side "paid" click.
- CGPA is self-reported in this MVP; production should pull it from the
  college ERP/academic API so it can't be faked at registration.
- `/admin` has no login in this demo build — add auth before real use.
- SQLite is fine for a fest-scale demo; move to Postgres for anything larger.
