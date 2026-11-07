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
