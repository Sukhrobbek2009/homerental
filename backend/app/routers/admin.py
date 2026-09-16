from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_admin
from .reviews import _to_review_out

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/verification-requests", response_model=list[schemas.UserOut])
def list_verification_requests(
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[models.User]:
    return (
        db.query(models.User)
        .filter(
            models.User.role == models.UserRole.host,
            models.User.verification_requested.is_(True),
            models.User.verified.is_(False),
        )
        .order_by(models.User.created_at.asc())
        .all()
    )


def _get_pending_host(user_id: str, db: Session) -> models.User:
    user = db.get(models.User, user_id)
    if user is None or user.role != models.UserRole.host:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Host not found")
    return user


@router.post("/verification-requests/{user_id}/approve", response_model=schemas.UserOut)
def approve_verification_request(
    user_id: str,
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> models.User:
    user = _get_pending_host(user_id, db)
    user.verified = True
    user.verification_requested = False
    db.commit()
    db.refresh(user)
    return user


@router.post("/verification-requests/{user_id}/reject", response_model=schemas.UserOut)
def reject_verification_request(
    user_id: str,
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> models.User:
    user = _get_pending_host(user_id, db)
    user.verification_requested = False
    db.commit()
    db.refresh(user)
    return user


@router.get("/reviews/flagged", response_model=list[schemas.ReviewOut])
def list_flagged_reviews(
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> list[schemas.ReviewOut]:
    reviews = (
        db.query(models.Review)
        .filter(models.Review.flagged.is_(True))
        .order_by(models.Review.created_at.desc())
        .all()
    )
    listings = {
        listing.id: listing
        for listing in db.query(models.Listing)
        .filter(models.Listing.id.in_({r.listing_id for r in reviews}))
        .all()
    }
    authors = {
        user.id: user
        for user in db.query(models.User).filter(models.User.id.in_({r.author_id for r in reviews})).all()
    }
    return [
        _to_review_out(
            review,
            authors.get(review.author_id),
            listings[review.listing_id].title if review.listing_id in listings else "Listing",
        )
        for review in reviews
    ]


@router.post("/reviews/{review_id}/clear", response_model=schemas.ReviewOut)
def clear_flagged_review(
    review_id: str,
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> schemas.ReviewOut:
    review = db.get(models.Review, review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")

    review.flagged = False
    db.commit()
    db.refresh(review)

    listing = db.get(models.Listing, review.listing_id)
    author = db.get(models.User, review.author_id)
    return _to_review_out(review, author, listing.title if listing is not None else "Listing")


@router.delete("/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_review(
    review_id: str,
    current_admin: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
) -> None:
    review = db.get(models.Review, review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")

    db.delete(review)
    db.commit()
