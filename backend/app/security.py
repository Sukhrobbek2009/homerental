from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token

from .config import settings

ALGORITHM = "HS256"

_google_request = google_requests.Request()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


class GoogleTokenError(Exception):
    pass


def verify_google_credential(credential: str, client_id: str) -> dict:
    """Verify a Google Identity Services ID token and return its claims.

    Raises GoogleTokenError if the token is malformed, expired, signed for a
    different client, or not issued by Google.
    """
    try:
        claims = google_id_token.verify_oauth2_token(credential, _google_request, client_id)
    except ValueError as exc:
        raise GoogleTokenError(str(exc)) from exc

    if claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise GoogleTokenError("Unexpected token issuer")

    return claims


def _create_token(subject: str, expires_delta: timedelta, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: str) -> str:
    return _create_token(
        user_id,
        timedelta(minutes=settings.access_token_expire_minutes),
        "access",
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        user_id,
        timedelta(days=settings.refresh_token_expire_days),
        "refresh",
    )


class InvalidTokenError(Exception):
    pass


def decode_token(token: str, expected_type: str) -> str:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc

    if payload.get("type") != expected_type:
        raise InvalidTokenError("Unexpected token type")

    subject = payload.get("sub")
    if not subject:
        raise InvalidTokenError("Token missing subject")

    return subject
