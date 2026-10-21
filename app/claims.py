
import os
import secrets
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    ACTIVE_STATUSES,
    CANCELLED,
    EXPIRED,
    HELD,
    PICKED_UP,
    Claim,
    Listing,
    utcnow,
)

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class ClaimError(Exception):
    """A claim or pickup could not go through; the message is shown to the user."""


def hold_minutes() -> int:
    return int(os.environ.get("HOLD_MINUTES", "15"))


def expire_stale_holds(db: Session, listing_id: int | None = None) -> None:
    """Mark held claims whose time ran out as expired."""
    stmt = (
        update(Claim)
        .where(Claim.status == HELD, Claim.expires_at <= utcnow())
        .values(status=EXPIRED)
    )
    if listing_id is not None:
        stmt = stmt.where(Claim.listing_id == listing_id)
    db.execute(stmt)


def portions_taken(db: Session, listing_id: int) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Claim)
        .where(Claim.listing_id == listing_id, Claim.status.in_(ACTIVE_STATUSES))
    )


def remaining_by_listing(db: Session, listing_ids: list[int]) -> dict[int, int]:
    """Portions still available for each listing, in one query."""
    if not listing_ids:
        return {}
    taken = dict(
        db.execute(
            select(Claim.listing_id, func.count())
            .where(Claim.listing_id.in_(listing_ids), Claim.status.in_(ACTIVE_STATUSES))
            .group_by(Claim.listing_id)
        ).all()
    )
    portions = dict(
        db.execute(select(Listing.id, Listing.portions).where(Listing.id.in_(listing_ids))).all()
    )
    return {lid: max(portions[lid] - taken.get(lid, 0), 0) for lid in listing_ids}


def claim_portion(db: Session, listing_id: int, user_id: int) -> Claim:
    """Hold one portion of a listing for a student. Raises ClaimError if it can't."""
    try:
        listing = db.scalar(select(Listing).where(Listing.id == listing_id).with_for_update())
        now = utcnow()
        if listing is None or listing.closed:
            raise ClaimError("That listing is no longer available.")
        if listing.available_until <= now:
            raise ClaimError("The pickup window for that listing has ended.")
        if listing.host_id == user_id:
            raise ClaimError("You can't claim food from your own listing.")

        expire_stale_holds(db, listing_id)

        already = db.scalar(
            select(Claim.id).where(
                Claim.listing_id == listing_id,
                Claim.user_id == user_id,
                Claim.status.in_(ACTIVE_STATUSES),
            )
        )
        if already:
            raise ClaimError("You already have a claim on this listing.")
        if portions_taken(db, listing_id) >= listing.portions:
            raise ClaimError("Sorry, all portions have been claimed.")

        claim = Claim(
            listing_id=listing_id,
            user_id=user_id,
            status=HELD,
            pickup_code="".join(secrets.choice(CODE_ALPHABET) for _ in range(4)),
            created_at=now,
            expires_at=min(now + timedelta(minutes=hold_minutes()), listing.available_until),
        )
        db.add(claim)
        db.commit() 
        return claim
    except ClaimError:
        db.rollback()  
        raise
    except IntegrityError:
        db.rollback()
        raise ClaimError("You already have a claim on this listing.")


def cancel_claim(db: Session, claim_id: int, user_id: int) -> None:
    claim = db.scalar(select(Claim).where(Claim.id == claim_id).with_for_update())
    if claim is None or claim.user_id != user_id or claim.status != HELD:
        db.rollback()
        raise ClaimError("That claim can't be cancelled.")
    claim.status = CANCELLED
    db.commit()


def confirm_pickup(db: Session, claim_id: int, host_id: int) -> Claim:
    """The host marks a claim as handed over."""
    claim = db.scalar(select(Claim).where(Claim.id == claim_id).with_for_update())
    if claim is None or claim.listing.host_id != host_id:
        db.rollback()
        raise ClaimError("Claim not found.")
    if claim.status == PICKED_UP:
        db.rollback()
        raise ClaimError("Already marked as picked up.")
    if claim.status != HELD or claim.expires_at <= utcnow():
        db.rollback()
        raise ClaimError("This claim expired or was cancelled, so the portion went back to the pool.")
    claim.status = PICKED_UP
    claim.picked_up_at = utcnow()
    db.commit()
    return claim
