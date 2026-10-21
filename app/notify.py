
import json
import os
import urllib.request
from datetime import timedelta

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import PICKED_UP, Claim, Listing, User, utcnow


def pick_recipients(db: Session, listing: Listing, limit: int) -> list[User]:
    week_ago = utcnow() - timedelta(days=7)
    recent_pickups = func.count(Claim.id)
    stmt = (
        select(User)
        .outerjoin(
            Claim,
            and_(
                Claim.user_id == User.id,
                Claim.status == PICKED_UP,
                Claim.picked_up_at >= week_ago,
            ),
        )
        .where(User.wants_alerts.is_(True), User.id != listing.host_id)
        .group_by(User.id)
        .order_by(recent_pickups.asc(), User.created_at.asc(), User.id.asc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


def send_email(to: str, subject: str, body: str) -> None:
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        print(f"\n--- EMAIL (not sent, no RESEND_API_KEY) ---\nTo: {to}\nSubject: {subject}\n\n{body}\n---\n")
        return
    request = urllib.request.Request(
        "https://api.resend.com/emails",
        data=json.dumps(
            {
                "from": os.environ.get("EMAIL_FROM", "Leftover <onboarding@resend.dev>"),
                "to": [to],
                "subject": subject,
                "text": body,
            }
        ).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(request, timeout=10).read()
    except Exception as exc:  
        print(f"Email to {to} failed: {exc}")


def notify_new_listing(listing_id: int) -> None:
    """Runs in the background after a host posts food."""
    base_url = os.environ.get("BASE_URL", "http://localhost:8000")
    limit = int(os.environ.get("ALERT_BATCH_SIZE", "25"))
    with SessionLocal() as db:
        listing = db.get(Listing, listing_id)
        if listing is None:
            return
        for user in pick_recipients(db, listing, limit):
            send_email(
                user.email,
                f"Free food: {listing.title} at {listing.location}",
                f"Hi {user.name},\n\n"
                f"{listing.portions} portions of {listing.title} are up for grabs at "
                f"{listing.location}.\n\n{listing.description}\n\n"
                f"Claim one here: {base_url}/\n\n"
                f"(Turn these emails off any time on the site.)",
            )
