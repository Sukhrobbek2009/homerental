from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


@router.get("/listing/{listing_id}", response_model=list[schemas.ReviewOut])
def list_listing_reviews(listing_id: str, db: Session = Depends(get_db)) -> list[models.Review]:
    return (
        db.query(models.Review)
        .filter(models.Review.listing_id == listing_id)
        .order_by(models.Review.created_at.desc())
        .all()
    )


@router.post("", response_model=schemas.ReviewOut, status_code=status.HTTP_201_CREATED)
def create_review(
    payload: schemas.ReviewCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.Review:
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
    return review
