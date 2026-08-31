from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..config import settings
from ..database import get_db
from ..deps import get_current_user
from ..security import (
    GoogleTokenError,
    InvalidTokenError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_google_credential,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue_tokens(user: models.User) -> schemas.TokenResponse:
    return schemas.TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
        user=schemas.UserOut.model_validate(user),
    )


@router.post("/signup", response_model=schemas.TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(payload: schemas.SignupRequest, db: Session = Depends(get_db)) -> schemas.TokenResponse:
    email = payload.email.lower()

    existing_filters = [models.User.email == email]
    if payload.phone:
        existing_filters.append(models.User.phone == payload.phone)

    existing = db.query(models.User).filter(or_(*existing_filters)).first()
    if existing is not None:
        if existing.email == email:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this email already exists")
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="An account with this phone number already exists")

    user = models.User(
        full_name=payload.full_name,
        email=email,
        phone=payload.phone,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _issue_tokens(user)


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)) -> schemas.TokenResponse:
    user = db.query(models.User).filter(models.User.email == payload.email.lower()).first()

    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account uses Google sign-in. Continue with Google instead.",
        )

    if not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been disabled")

    return _issue_tokens(user)


@router.post("/google", response_model=schemas.TokenResponse)
def google_auth(payload: schemas.GoogleAuthRequest, db: Session = Depends(get_db)) -> schemas.TokenResponse:
    if not settings.google_client_id:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Google sign-in is not configured on this server yet",
        )

    try:
        claims = verify_google_credential(payload.credential, settings.google_client_id)
    except GoogleTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google credential")

    if not claims.get("email_verified"):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Google account email is not verified")

    google_sub = claims["sub"]
    email = claims["email"].lower()

    user = db.query(models.User).filter(models.User.google_sub == google_sub).first()

    if user is None:
        user = db.query(models.User).filter(models.User.email == email).first()
        if user is not None:
            user.google_sub = google_sub
        else:
            user = models.User(
                full_name=claims.get("name") or email.split("@")[0],
                email=email,
                google_sub=google_sub,
                password_hash=None,
                role=models.UserRole.renter,
            )
            db.add(user)
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="This account has been disabled")

    return _issue_tokens(user)


@router.post("/refresh", response_model=schemas.AccessTokenResponse)
def refresh(payload: schemas.RefreshRequest, db: Session = Depends(get_db)) -> schemas.AccessTokenResponse:
    try:
        user_id = decode_token(payload.refresh_token, expected_type="refresh")
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    user = db.get(models.User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

    return schemas.AccessTokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=schemas.UserOut)
def read_me(current_user: models.User = Depends(get_current_user)) -> models.User:
    return current_user


@router.patch("/me/role", response_model=schemas.UserOut)
def update_role(
    payload: schemas.RoleUpdateRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.User:
    current_user.role = payload.role
    db.commit()
    db.refresh(current_user)
    return current_user
