import threading
from datetime import timedelta

import pytest

from app import claims
from app.auth import hash_password
from app.db import SessionLocal
from app.models import EXPIRED, HELD, PICKED_UP, Claim, Listing, User, utcnow
from app.notify import pick_recipients


def make_user(db, name, host=False):
    u = User(name=name, email=f"{name}@school.edu", password_hash=hash_password("password123"), is_host=host)
    db.add(u)
    db.commit()
    return u


def make_listing(db, host, portions=3, hours=2):
    l = Listing(host_id=host.id, title="Pizza", location="Union", portions=portions,
                available_until=utcnow() + timedelta(hours=hours))
    db.add(l)
    db.commit()
    return l


def test_claim_reduces_remaining(db):
    host, alice = make_user(db, "host", host=True), make_user(db, "alice")
    listing = make_listing(db, host, portions=3)
    c = claims.claim_portion(db, listing.id, alice.id)
    assert c.status == HELD and len(c.pickup_code) == 4
    assert claims.remaining_by_listing(db, [listing.id]) == {listing.id: 2}


def test_cannot_claim_twice(db):
    host, alice = make_user(db, "host", host=True), make_user(db, "alice")
    listing = make_listing(db, host)
    claims.claim_portion(db, listing.id, alice.id)
    with pytest.raises(claims.ClaimError, match="already"):
        claims.claim_portion(db, listing.id, alice.id)


def test_sold_out(db):
    host, alice, bob = make_user(db, "host", True), make_user(db, "alice"), make_user(db, "bob")
    listing = make_listing(db, host, portions=1)
    claims.claim_portion(db, listing.id, alice.id)
    with pytest.raises(claims.ClaimError, match="all portions"):
        claims.claim_portion(db, listing.id, bob.id)


def test_expired_hold_frees_the_portion(db):
    host, alice, bob = make_user(db, "host", True), make_user(db, "alice"), make_user(db, "bob")
    listing = make_listing(db, host, portions=1)
    first = claims.claim_portion(db, listing.id, alice.id)
    first.expires_at = utcnow() - timedelta(seconds=1)  # pretend alice never showed up
    db.commit()
    second = claims.claim_portion(db, listing.id, bob.id)
    db.refresh(first)
    assert first.status == EXPIRED and second.status == HELD
    with pytest.raises(claims.ClaimError, match="expired"):
        claims.confirm_pickup(db, first.id, host.id)


def test_host_confirms_pickup(db):
    host, alice = make_user(db, "host", True), make_user(db, "alice")
    listing = make_listing(db, host)
    c = claims.claim_portion(db, listing.id, alice.id)
    claims.confirm_pickup(db, c.id, host.id)
    db.refresh(c)
    assert c.status == PICKED_UP and c.picked_up_at is not None


def test_many_students_race_for_the_last_portion():
    """30 students hit Claim at the same instant; exactly 2 portions exist."""
    with SessionLocal() as db:
        host = make_user(db, "host", True)
        students = [make_user(db, f"s{i}") for i in range(30)]
        listing = make_listing(db, host, portions=2)
        listing_id, student_ids = listing.id, [s.id for s in students]

    start = threading.Barrier(len(student_ids))
    results = []

    def attempt(uid):
        with SessionLocal() as db:
            start.wait()  # line everyone up, then go at once
            try:
                claims.claim_portion(db, listing_id, uid)
                results.append("ok")
            except claims.ClaimError:
                results.append("rejected")

    threads = [threading.Thread(target=attempt, args=(uid,)) for uid in student_ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert results.count("ok") == 2
    assert results.count("rejected") == 28
    with SessionLocal() as db:
        assert db.query(Claim).filter_by(listing_id=listing_id).count() == 2


def test_alert_priority_favours_students_with_fewer_recent_pickups(db):
    host = make_user(db, "host", True)
    regular, newcomer = make_user(db, "regular"), make_user(db, "newcomer")
    opted_out = make_user(db, "quiet")
    opted_out.wants_alerts = False
    db.commit()
    old = make_listing(db, host, portions=5)
    c = claims.claim_portion(db, old.id, regular.id)
    claims.confirm_pickup(db, c.id, host.id)

    new = make_listing(db, host)
    order = [u.name for u in pick_recipients(db, new, limit=10)]
    assert order == ["newcomer", "regular"]  # host and opted-out user excluded
    assert [u.name for u in pick_recipients(db, new, limit=1)] == ["newcomer"]
