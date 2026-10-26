import os
from collections import Counter
from datetime import timedelta
from zoneinfo import ZoneInfo

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import claims as claim_logic
from .auth import verify_password
from .db import get_db
from .models import ACTIVE_STATUSES, PICKED_UP, Claim, Listing, User, utcnow

TOKEN_MINUTES = 60
ALGORITHM = "HS256"

router = APIRouter(prefix="/api", tags=["api"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/token")


def _secret() -> str:
    return os.environ.get("SECRET_KEY", "dev-only-secret-change-me-before-deploying")


def create_token(user: User) -> str:
    now = utcnow()
    payload = {"sub": str(user.id), "iat": now, "exp": now + timedelta(minutes=TOKEN_MINUTES)}
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def api_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not logged in, or your session expired.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise unauthorized
    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise unauthorized
    return user


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class Me(BaseModel):
    id: int
    name: str
    email: str
    is_host: bool


class ListingOut(BaseModel):
    id: int
    title: str
    location: str
    description: str
    portions: int
    remaining: int
    available_until: str


class ClaimOut(BaseModel):
    id: int
    listing_id: int
    listing_title: str
    location: str
    status: str
    pickup_code: str
    expires_at: str


class DayStats(BaseModel):
    date: str
    portions_posted: int
    meals_rescued: int


def _claim_out(c: Claim) -> ClaimOut:
    return ClaimOut(
        id=c.id, listing_id=c.listing_id, listing_title=c.listing.title, location=c.listing.location,
        status=c.status, pickup_code=c.pickup_code, expires_at=c.expires_at.isoformat(),
    )


@router.post("/token", response_model=Token)
def login_for_token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == form.username.strip().lower()))
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    return Token(access_token=create_token(user), expires_in=TOKEN_MINUTES * 60)


@router.get("/listings", response_model=list[ListingOut])
def list_listings(db: Session = Depends(get_db)):
    claim_logic.expire_stale_holds(db)
    db.commit()
    listings = list(
        db.scalars(
            select(Listing)
            .where(Listing.closed.is_(False), Listing.available_until > utcnow())
            .order_by(Listing.available_until)
        )
    )
    remaining = claim_logic.remaining_by_listing(db, [l.id for l in listings])
    return [
        ListingOut(
            id=l.id, title=l.title, location=l.location, description=l.description,
            portions=l.portions, remaining=remaining[l.id], available_until=l.available_until.isoformat(),
        )
        for l in listings
    ]


@router.get("/me", response_model=Me)
def me(user: User = Depends(api_user)):
    return Me(id=user.id, name=user.name, email=user.email, is_host=user.is_host)


@router.get("/me/claims", response_model=list[ClaimOut])
def my_claims(user: User = Depends(api_user), db: Session = Depends(get_db)):
    claim_logic.expire_stale_holds(db)
    db.commit()
    rows = db.scalars(
        select(Claim)
        .where(Claim.user_id == user.id, Claim.status.in_(ACTIVE_STATUSES))
        .order_by(Claim.created_at.desc())
        .limit(20)
    )
    return [_claim_out(c) for c in rows]


@router.post("/listings/{listing_id}/claim", response_model=ClaimOut, status_code=201)
def claim_listing(listing_id: int, user: User = Depends(api_user), db: Session = Depends(get_db)):
    try:
        return _claim_out(claim_logic.claim_portion(db, listing_id, user.id))
    except claim_logic.ClaimError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/stats/daily", response_model=list[DayStats])
def daily_stats(days: int = 30, db: Session = Depends(get_db)):
    days = max(1, min(days, 365))
    tz = ZoneInfo(os.environ.get("TIMEZONE", "America/New_York"))
    today = utcnow().astimezone(tz).date()
    start = today - timedelta(days=days - 1)
    since = utcnow() - timedelta(days=days + 1)

    posted = Counter()
    for created, portions in db.execute(
        select(Listing.created_at, Listing.portions).where(Listing.created_at >= since)
    ):
        posted[created.astimezone(tz).date()] += portions
    rescued = Counter(
        picked.astimezone(tz).date()
        for picked in db.scalars(
            select(Claim.picked_up_at).where(Claim.status == PICKED_UP, Claim.picked_up_at >= since)
        )
    )
    return [
        DayStats(date=d.isoformat(), portions_posted=posted[d], meals_rescued=rescued[d])
        for d in (start + timedelta(days=i) for i in range(days))
    ]
