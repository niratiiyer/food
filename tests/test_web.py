from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.main import TZ, app


def signup(client, name, host=False):
    data = {"name": name, "email": f"{name}@school.edu", "password": "password123"}
    if host:
        data["is_host"] = "true"
    return client.post("/signup", data=data)


def test_host_posts_and_student_claims(capsys):
    host, student = TestClient(app), TestClient(app)
    signup(host, "hana", host=True)
    signup(student, "sam")

    until = (datetime.now(TZ) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    r = host.post("/host/listings", data={"title": "Bagels", "location": "Library steps",
                                          "portions": "4", "available_until": until})
    assert "Bagels" in r.text and "now on the home page" in r.text
    assert "notify" not in r.text
    assert "Free food: Bagels" not in capsys.readouterr().out  # nobody was emailed

    r = student.get("/")
    assert "Bagels" in r.text and "4 <span>of 4 left" in r.text
    assert "Email alerts" not in r.text
    r = student.post("/listings/1/claim")
    assert "Your pickup code is" in r.text and "3 <span>of 4 left" in r.text

    r = host.get("/host")
    assert "sam" in r.text and "held until" in r.text
    r = host.post("/host/claims/1/pickup")
    assert "picked up" in r.text

    r = student.get("/stats")
    assert "Meals rescued" in r.text


def test_students_cannot_open_host_page():
    student = TestClient(app)
    signup(student, "sam")
    assert student.get("/host").status_code == 403


def test_logged_out_claim_redirects_to_login():
    r = TestClient(app).post("/listings/1/claim")
    assert r.url.path == "/login"


def test_email_alerts_can_be_turned_back_on(monkeypatch, capsys):
    monkeypatch.setenv("EMAIL_ALERTS", "on")
    host, student = TestClient(app), TestClient(app)
    signup(host, "hana", host=True)
    signup(student, "sam")
    until = (datetime.now(TZ) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
    r = host.post("/host/listings", data={"title": "Bagels", "location": "Library steps",
                                          "portions": "4", "available_until": until})
    assert "Students are being notified" in r.text
    assert "Free food: Bagels" in capsys.readouterr().out
    assert "Email alerts are" in student.get("/").text
