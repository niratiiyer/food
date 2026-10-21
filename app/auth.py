
import hashlib
import hmac
import os
import secrets

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import User


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), n=2**14, r=8, p=1)
    return hmac.compare_digest(digest.hex(), digest_hex)


def email_allowed(email: str) -> bool:
    domain = os.environ.get("ALLOWED_EMAIL_DOMAIN", "").strip().lower()
    return not domain or email.lower().endswith("@" + domain)


def current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = request.session.get("user_id")
    return db.get(User, user_id) if user_id else None


class LoginRequired(Exception):
    pass


def require_user(user: User | None = Depends(current_user)) -> User:
    if user is None:
        raise LoginRequired()
    return user


def require_host(user: User = Depends(require_user)) -> User:
    if not user.is_host:
        raise HTTPException(status_code=403, detail="Only event hosts can do that.")
    return user
