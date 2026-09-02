from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


def _to_review_out(review: models.Review, author: models.User | None) -> schemas.ReviewOut:
    return schemas.ReviewOut(
        id=review.id,
        booking_id=review.booking_id,
        listing_id=review.listing_id,
        author_id=review.author_id,
        author_name=author.full_name if author is not None else "Guest",
        rating=review.rating,
        comment=review.comment,
        created_at=review.created_at,
    )


@router.get("/listing/{listing_id}", response_model=list[schemas.ReviewOut])
def list_listing_reviews(listing_id: str, db: Session = Depends(get_db)) -> list[schemas.ReviewOut]:
    reviews = (
        db.query(models.Review)
        .filter(models.Review.listing_id == listing_id)
        .order_by(models.Review.created_at.desc())
        .all()
    )
    return [_to_review_out(review, db.get(models.User, review.author_id)) for review in reviews]


@router.post("", response_model=schemas.ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(
    payload: schemas.ReviewCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.ReviewOut:
    booking = db.get(models.Booking, payload.booking_id)
    if booking is None or booking.renter_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    if booking.status != models.BookingStatus.completed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can only review a completed booking",
        )

    existing = db.query(models.Review).filter(models.Review.booking_id == booking.id).first()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="This booking already has a review")

    review = models.Review(
        booking_id=booking.id,
        listing_id=booking.listing_id,
        author_id=current_user.id,
        rating=payload.rating,
        comment=payload.comment,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    return _to_review_out(review, current_user)
