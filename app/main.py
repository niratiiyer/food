import os
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import BackgroundTasks, Depends, FastAPI, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware

from . import claims as claim_logic
from .auth import (
    LoginRequired,
    current_user,
    email_allowed,
    hash_password,
    require_host,
    require_user,
    verify_password,
)
from .db import Base, engine, get_db
from .models import ACTIVE_STATUSES, HELD, PICKED_UP, Claim, Listing, User, utcnow
from .api import router as api_router
from .notify import notify_new_listing
from .observability import RequestLogMiddleware

HERE = Path(__file__).parent
TZ = ZoneInfo(os.environ.get("TIMEZONE", "America/New_York"))


Base.metadata.create_all(engine)

app = FastAPI(title="Leftover")
app.add_middleware(RequestLogMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ.get("SECRET_KEY", "dev-only-secret-change-me-before-deploying"),
    same_site="lax",
    https_only=os.environ.get("BASE_URL", "").startswith("https://"),
    max_age=60 * 60 * 24 * 30,
)
app.include_router(api_router)
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
templates = Jinja2Templates(directory=HERE / "templates")
templates.env.filters["local"] = lambda dt: dt.astimezone(TZ).strftime("%a %b %-d, %-I:%M %p")


def alerts_on() -> bool:
    """Email alerts are off unless EMAIL_ALERTS=on is set (sending email to everyone costs money)."""
    return os.environ.get("EMAIL_ALERTS", "off").strip().lower() == "on"


templates.env.globals["alerts_on"] = alerts_on


def flash(request: Request, message: str) -> None:
    request.session["flash"] = message


def back_to(path: str) -> RedirectResponse:
    return RedirectResponse(path, status_code=303)


def render(request: Request, name: str, user: User | None, **context):
    return templates.TemplateResponse(
        request,
        name,
        {"user": user, "flash": request.session.pop("flash", None), **context},
    )


@app.exception_handler(LoginRequired)
def _login_required(request: Request, exc: LoginRequired):
    flash(request, "Please log in first.")
    return back_to("/login")




@app.get("/")
def home(request: Request, db: Session = Depends(get_db), user: User | None = Depends(current_user)):
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
    my_claims = []
    if user:
        my_claims = list(
            db.scalars(
                select(Claim)
                .where(Claim.user_id == user.id, Claim.status.in_(ACTIVE_STATUSES))
                .order_by(Claim.created_at.desc())
                .limit(10)
            )
        )
    claimed_ids = {c.listing_id for c in my_claims}
    return render(
        request, "index.html", user,
        listings=listings, remaining=remaining, my_claims=my_claims, claimed_ids=claimed_ids,
    )


@app.post("/listings/{listing_id}/claim")
def claim(listing_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    try:
        c = claim_logic.claim_portion(db, listing_id, user.id)
        flash(
            request,
            f"Claimed! Your pickup code is {c.pickup_code}. "
            f"Pick up by {templates.env.filters['local'](c.expires_at)}.",
        )
    except claim_logic.ClaimError as e:
        flash(request, str(e))
    return back_to("/")


@app.post("/claims/{claim_id}/cancel")
def cancel(claim_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    try:
        claim_logic.cancel_claim(db, claim_id, user.id)
        flash(request, "Claim cancelled. Thanks for freeing it up for someone else.")
    except claim_logic.ClaimError as e:
        flash(request, str(e))
    return back_to("/")


@app.post("/settings/alerts")
def toggle_alerts(request: Request, db: Session = Depends(get_db), user: User = Depends(require_user)):
    user.wants_alerts = not user.wants_alerts
    db.commit()
    flash(request, "Email alerts turned " + ("on." if user.wants_alerts else "off."))
    return back_to("/")




@app.get("/signup")
def signup_page(request: Request, user: User | None = Depends(current_user)):
    return render(request, "signup.html", user, domain=os.environ.get("ALLOWED_EMAIL_DOMAIN", ""))


@app.post("/signup")
def signup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    is_host: bool = Form(False),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    if not email_allowed(email):
        flash(request, f"Please use your @{os.environ.get('ALLOWED_EMAIL_DOMAIN')} email.")
        return back_to("/signup")
    if len(password) < 8:
        flash(request, "Password must be at least 8 characters.")
        return back_to("/signup")
    if db.scalar(select(User).where(User.email == email)):
        flash(request, "That email already has an account. Try logging in.")
        return back_to("/login")
    user = User(name=name.strip(), email=email, password_hash=hash_password(password), is_host=is_host)
    db.add(user)
    db.commit()
    request.session["user_id"] = user.id
    flash(request, f"Welcome, {user.name}!")
    return back_to("/host" if is_host else "/")


@app.get("/login")
def login_page(request: Request, user: User | None = Depends(current_user)):
    return render(request, "login.html", user)


@app.post("/login")
def login(request: Request, email: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not verify_password(password, user.password_hash):
        flash(request, "Wrong email or password.")
        return back_to("/login")
    request.session["user_id"] = user.id
    return back_to("/host" if user.is_host else "/")


@app.post("/logout")
def logout(request: Request):
    request.session.clear()
    return back_to("/")




@app.get("/host")
def host_page(request: Request, db: Session = Depends(get_db), user: User = Depends(require_host)):
    claim_logic.expire_stale_holds(db)
    db.commit()
    listings = list(
        db.scalars(select(Listing).where(Listing.host_id == user.id).order_by(Listing.created_at.desc()).limit(20))
    )
    remaining = claim_logic.remaining_by_listing(db, [l.id for l in listings])
    default_until = (datetime.now(TZ) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    return render(
        request, "host.html", user,
        listings=listings, remaining=remaining, default_until=default_until, now=utcnow(),
        HELD=HELD, PICKED_UP=PICKED_UP,
    )


@app.post("/host/listings")
def create_listing(
    request: Request,
    background: BackgroundTasks,
    title: str = Form(...),
    location: str = Form(...),
    portions: int = Form(...),
    available_until: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_host),
):
    until = datetime.fromisoformat(available_until).replace(tzinfo=TZ)
    if portions < 1 or portions > 500:
        flash(request, "Portions must be between 1 and 500.")
        return back_to("/host")
    if until <= utcnow():
        flash(request, "The pickup deadline has to be in the future.")
        return back_to("/host")
    listing = Listing(
        host_id=user.id, title=title.strip(), location=location.strip(),
        description=description.strip(), portions=portions, available_until=until,
    )
    db.add(listing)
    db.commit()
    if alerts_on():
        background.add_task(notify_new_listing, listing.id)  # runs after the page responds
        flash(request, "Posted! Students are being notified.")
    else:
        flash(request, "Posted! It's now on the home page for students to claim.")
    return back_to("/host")


@app.post("/host/claims/{claim_id}/pickup")
def mark_picked_up(claim_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_host)):
    try:
        c = claim_logic.confirm_pickup(db, claim_id, user.id)
        flash(request, f"Marked {c.pickup_code} as picked up.")
    except claim_logic.ClaimError as e:
        flash(request, str(e))
    return back_to("/host")


@app.post("/host/listings/{listing_id}/close")
def close_listing(listing_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_host)):
    listing = db.get(Listing, listing_id)
    if listing and listing.host_id == user.id:
        listing.closed = True
        db.commit()
        flash(request, "Listing closed.")
    return back_to("/host")




@app.get("/stats")
def stats(request: Request, db: Session = Depends(get_db), user: User | None = Depends(current_user)):
    week_ago = utcnow() - timedelta(days=7)
    picked = select(func.count()).select_from(Claim).where(Claim.status == PICKED_UP)
    numbers = {
        "Meals rescued": db.scalar(picked),
        "Meals rescued this week": db.scalar(picked.where(Claim.picked_up_at >= week_ago)),
        "Students fed": db.scalar(select(func.count(distinct(Claim.user_id))).where(Claim.status == PICKED_UP)),
        "Food listings posted": db.scalar(select(func.count()).select_from(Listing)),
        "Event hosts": db.scalar(select(func.count()).select_from(User).where(User.is_host.is_(True))),
        "Signed-up users": db.scalar(select(func.count()).select_from(User)),
    }
    return render(request, "stats.html", user, numbers=numbers)


@app.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(select(1))
    return {"status": "ok"}


@app.get("/healthz")
def healthz():
    return {"ok": True}
