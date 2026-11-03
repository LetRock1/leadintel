"""Email goes out through a real SMTP conversation: a tiny mail server runs on this computer for the test (no
packages, no internet), and the CRM's mailer talks to it the way it talks to Gmail or any other mail server."""

from __future__ import annotations

import email
import smtplib
import socketserver
import threading

import pytest
from support import API

from app.services import mailer


class _Handler(socketserver.StreamRequestHandler):
    """Just enough SMTP for smtplib: greeting, EHLO, MAIL, RCPT, DATA, QUIT (no AUTH, no TLS)."""

    def handle(self):
        def say(text: str) -> None:
            self.wfile.write(text.encode() + b"\r\n")

        say("220 tiny test mail server")
        sender, rcpts = None, []
        while True:
            line = self.rfile.readline()
            if not line:
                return
            cmd = line.decode("utf-8", "replace").strip()
            word = cmd.split(" ", 1)[0].upper()
            if word in ("EHLO", "HELO"):
                say("250 tiny")
            elif cmd.upper().startswith("MAIL FROM:"):
                sender = cmd[10:].strip()
                say("250 OK")
            elif cmd.upper().startswith("RCPT TO:"):
                rcpts.append(cmd[8:].strip())
                say("250 OK")
            elif word == "DATA":
                say("354 End data with <CR><LF>.<CR><LF>")
                body = []
                while True:
                    part = self.rfile.readline()
                    if part in (b".\r\n", b".\n", b""):
                        break
                    body.append(part[1:] if part.startswith(b"..") else part)
                self.server.received.append({"from": sender, "to": rcpts, "data": b"".join(body)})
                sender, rcpts = None, []
                say("250 OK: queued")
            elif word == "QUIT":
                say("221 Bye")
                return
            elif word in ("RSET", "NOOP"):
                say("250 OK")
            else:
                say("502 Not implemented")


class TinyMailServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True

    def __init__(self):
        super().__init__(("127.0.0.1", 0), _Handler)
        self.received: list[dict] = []


@pytest.fixture
def mail_server(monkeypatch):
    server = TinyMailServer()
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setattr(mailer, "SMTP_HOST", "127.0.0.1")
    monkeypatch.setattr(mailer, "SMTP_PORT", server.server_address[1])
    monkeypatch.setattr(mailer, "SMTP_SECURITY", "none")
    monkeypatch.setattr(mailer, "SERVER", "The mail server")
    monkeypatch.setattr(mailer, "GMAIL_USER", "crm@example.com")
    monkeypatch.setattr(mailer, "GMAIL_PASS", "")
    monkeypatch.setattr(mailer, "_paused_until", {"t": 0.0})
    yield server
    server.shutdown()
    server.server_close()


def test_a_local_relay_needs_only_the_senders_address(mail_server):
    assert mailer.configured()
    ok, message = mailer.send_otp_email("learner@example.com", "482913", "Asha")
    assert ok and message == "Sent to learner@example.com"
    assert len(mail_server.received) == 1
    got = mail_server.received[0]
    assert got["from"] == "<crm@example.com>" and got["to"] == ["<learner@example.com>"]
    msg = email.message_from_bytes(got["data"])
    assert msg["Subject"] == "Your X Education verification code: 482913"
    assert msg["From"] == "X Education <crm@example.com>" and msg["To"] == "learner@example.com"
    kinds = [p.get_content_type() for p in msg.walk() if not p.is_multipart()]
    assert kinds == ["text/plain", "text/html"]  # a plain part for every mail client, and the designed one
    assert all("482913" in p.get_payload(decode=True).decode() for p in msg.walk() if not p.is_multipart())


def test_the_purchase_confirmation_says_nothing_was_charged(mail_server):
    ok, _ = mailer.send_purchase_confirmation_email(
        "learner@example.com", "Asha", ["Finance & Banking"], "your course enquiry", 45000.0, 10
    )
    assert ok
    msg = email.message_from_bytes(mail_server.received[-1]["data"])
    text = next(p for p in msg.walk() if p.get_content_type() == "text/plain").get_payload(decode=True).decode()
    assert "nothing was charged" in text and "Rs 45,000.00" in text


def test_a_mail_server_that_is_down_pauses_email_instead_of_waiting_on_every_message(mail_server):
    port = mail_server.server_address[1]
    mail_server.shutdown()
    mail_server.server_close()  # nothing listens on the port any more
    ok, message = mailer.send_simple_email("a@example.com", "One", "Body")
    assert not ok and "Could not reach the mail server" in message and port
    ok, message = mailer.send_simple_email("b@example.com", "Two", "Body")
    assert not ok and "paused" in message


def test_starttls_is_used_and_the_login_sent_when_a_password_is_set(monkeypatch):
    calls = []

    class Fake:
        def __init__(self, host, port, timeout=None):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user))

        def sendmail(self, sender, to, message):
            calls.append(("send", to))

    monkeypatch.setattr(smtplib, "SMTP", Fake)
    monkeypatch.setattr(mailer, "SMTP_HOST", "smtp.office365.com")
    monkeypatch.setattr(mailer, "SMTP_PORT", 587)
    monkeypatch.setattr(mailer, "SMTP_SECURITY", "starttls")
    monkeypatch.setattr(mailer, "GMAIL_USER", "team@example.com")
    monkeypatch.setattr(mailer, "GMAIL_PASS", "app-password")
    monkeypatch.setattr(mailer, "_paused_until", {"t": 0.0})
    assert mailer.send_simple_email("learner@example.com", "Hello", "Body")[0]
    assert calls == [
        ("connect", "smtp.office365.com", 587),
        ("starttls",),
        ("login", "team@example.com"),
        ("send", "learner@example.com"),
    ]


def test_a_campaign_keeps_the_emails_a_dead_mail_server_did_not_take_and_sends_them_again(
    mail_server, client, owner, new_learner
):
    from support import CRM

    from app import db

    port = mail_server.server_address[1]
    for i in range(3):
        new_learner(f"Campaign Reader {i}")
    r = client.post(
        f"{CRM}/campaigns",
        json={
            "name": "Mail server test",
            "tier": "All leads",
            "subject": "Weekend batch",
            "body": "Hi {first_name}, the weekend batch starts Saturday.",
            "scheduled_at": "2030-01-01T09:00",
            "holdout_share": 0,
        },
        headers=owner["headers"],
    )
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    mail_server.shutdown()
    mail_server.server_close()  # the mail server is down while the campaign goes out
    r = client.post(f"{CRM}/campaigns/{cid}/send-now", headers=owner["headers"])
    assert r.status_code == 200, r.text

    def mine():
        c = next(
            x for x in client.get(f"{CRM}/campaigns", headers=owner["headers"]).json()["campaigns"] if x["id"] == cid
        )
        return c

    c = mine()
    # every real recipient's email failed (simulated learners' emails are only recorded, never sent)
    real = db.fetchall(
        """SELECT es.error, u.email FROM email_sends es JOIN users u ON u.id = es.user_id
           WHERE es.campaign_id=? AND u.email NOT LIKE '%.test'""",
        (cid,),
    )
    assert len(real) >= 1 and all(r["error"] for r in real)  # (some test learners are in the control group)
    assert c["failed"] == len(real) and c["status"] == "sent_with_errors"
    delivered_before = c["delivered"]
    assert "mail server" in (c["failed_reason"] or "") or "paused" in (c["failed_reason"] or "")
    lead = client.get(f"{CRM}/leads", params={"search": real[0]["email"]}, headers=owner["headers"]).json()
    page = client.get(f"{CRM}/leads/{lead['leads'][0]['id']}", headers=owner["headers"]).json()
    assert page["emails"][0]["error"]  # the lead page says it was not sent

    # the mail server is back (and the five-minute pause is over): the failed emails go out, same links
    again = TinyMailServer.__new__(TinyMailServer)
    socketserver.ThreadingTCPServer.__init__(again, ("127.0.0.1", port), _Handler)
    again.received = []
    threading.Thread(target=again.serve_forever, daemon=True).start()
    try:
        mailer._paused_until["t"] = 0.0
        tokens = {
            r["token"]
            for r in db.fetchall("SELECT token FROM email_sends WHERE campaign_id=? AND error IS NOT NULL", (cid,))
        }
        r = client.post(f"{CRM}/campaigns/{cid}/send-failed", headers=owner["headers"])
        assert r.status_code == 200, r.text
        assert r.json()["still_failed"] == 0 and r.json()["sent"] == len(tokens)
        c = mine()
        assert c["failed"] == 0 and c["delivered"] == delivered_before + len(tokens) and c["status"] == "sent"
        bodies = [m["data"].decode("utf-8", "replace") for m in again.received]
        assert len(bodies) == len(tokens)
        assert all(any(t in b for b in bodies) for t in tokens)  # each email keeps its own tracked link
    finally:
        again.shutdown()
        again.server_close()


def _server_on(port: int) -> TinyMailServer:
    server = TinyMailServer.__new__(TinyMailServer)
    socketserver.ThreadingTCPServer.__init__(server, ("127.0.0.1", port), _Handler)
    server.received = []
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_failed_emails_are_tried_again_automatically_but_not_forever_or_after_an_opt_out(
    mail_server, client, owner, new_learner
):
    from app import db
    from app.services import outreach

    port = mail_server.server_address[1]
    mail_server.shutdown()
    mail_server.server_close()  # down
    a, b, c = new_learner("Retry One"), new_learner("Retry Two"), new_learner("Retry Three")
    subject = f"Retry test {a['user']['id']}"  # its own subject: other tests' emails are not part of it
    for who in (a, b, c):
        ok, _ = outreach.send_tracked_email(who["user"]["id"], None, who["email"], subject, "Hi there.")
        assert not ok
        mailer._paused_until["t"] = 0.0  # each send finds the server down for itself
    rows = {r["user_id"]: r for r in db.fetchall("SELECT * FROM email_sends WHERE subject=?", (subject,))}
    assert all(rows[w["user"]["id"]]["error"] and rows[w["user"]["id"]]["attempts"] == 1 for w in (a, b, c))
    mailer._paused_until["t"] = 10**12
    assert outreach.retry_failed() == {"tried": 0, "sent": 0}  # nothing is tried while sending is paused
    # b opts out in the meantime; c's email was already tried six times
    client.put(f"{API}/profile/preferences", json={"do_not_email": True}, headers=b["headers"])
    db.execute("UPDATE email_sends SET attempts=6 WHERE user_id=? AND subject=?", (c["user"]["id"], subject))
    server = _server_on(port)
    try:
        mailer._paused_until["t"] = 0.0
        out = outreach.retry_failed()
        assert out["sent"] >= 1
        after = {r["user_id"]: r for r in db.fetchall("SELECT * FROM email_sends WHERE subject=?", (subject,))}
        assert after[a["user"]["id"]]["error"] is None and after[a["user"]["id"]]["attempts"] == 2
        assert after[b["user"]["id"]]["error"] and after[b["user"]["id"]]["attempts"] == 1  # opted out: left alone
        assert after[c["user"]["id"]]["attempts"] == 6  # six tries are enough
        assert [m["to"] for m in server.received if subject.encode() in m["data"]] == [[f"<{a['email']}>"]]
    finally:
        server.shutdown()
        server.server_close()
