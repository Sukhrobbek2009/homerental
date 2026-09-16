from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


def _to_review_out(
    review: models.Review,
    author: models.User | None,
    listing_title: str = "Listing",
) -> schemas.ReviewOut:
    return schemas.ReviewOut(
        id=review.id,
        booking_id=review.booking_id,
        listing_id=review.listing_id,
        listing_title=listing_title,
        author_id=review.author_id,
        author_name=author.full_name if author is not None else "Guest",
        rating=review.rating,
        comment=review.comment,
        host_reply=review.host_reply,
        flagged=review.flagged,
        created_at=review.created_at,
    )


def _titles_by_listing_id(db: Session, listing_ids: set[str]) -> dict[str, str]:
    if not listing_ids:
        return {}
    listings = db.query(models.Listing).filter(models.Listing.id.in_(listing_ids)).all()
    return {listing.id: listing.title for listing in listings}


@router.get("/mine", response_model=list[schemas.ReviewOut])
def list_my_reviews(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[schemas.ReviewOut]:
    reviews = (
        db.query(models.Review)
        .filter(models.Review.author_id == current_user.id)
        .order_by(models.Review.created_at.desc())
        .all()
    )
    titles = _titles_by_listing_id(db, {review.listing_id for review in reviews})
    return [_to_review_out(review, current_user, titles.get(review.listing_id, "Listing")) for review in reviews]


@router.get("/hosted", response_model=list[schemas.ReviewOut])
def list_hosted_reviews(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[schemas.ReviewOut]:
    """Reviews left on any listing this host owns, so they can reply to them."""
    listing_ids = [
        row[0] for row in db.query(models.Listing.id).filter(models.Listing.host_id == current_user.id).all()
    ]
    if not listing_ids:
        return []

    reviews = (
        db.query(models.Review)
        .filter(models.Review.listing_id.in_(listing_ids))
        .order_by(models.Review.created_at.desc())
        .all()
    )
    titles = _titles_by_listing_id(db, set(listing_ids))
    authors = {
        user.id: user
        for user in db.query(models.User).filter(models.User.id.in_({r.author_id for r in reviews})).all()
    }
    return [
        _to_review_out(review, authors.get(review.author_id), titles.get(review.listing_id, "Listing"))
        for review in reviews
    ]


@router.get("/listing/{listing_id}", response_model=list[schemas.ReviewOut])
def list_listing_reviews(listing_id: str, db: Session = Depends(get_db)) -> list[schemas.ReviewOut]:
    listing = db.get(models.Listing, listing_id)
    listing_title = listing.title if listing is not None else "Listing"
    reviews = (
        db.query(models.Review)
        .filter(models.Review.listing_id == listing_id)
        .order_by(models.Review.created_at.desc())
        .all()
    )
    return [
        _to_review_out(review, db.get(models.User, review.author_id), listing_title) for review in reviews
    ]


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

    listing = db.get(models.Listing, review.listing_id)
    return _to_review_out(review, current_user, listing.title if listing is not None else "Listing")


@router.post("/{review_id}/reply", response_model=schemas.ReviewOut)
def reply_to_review(
    review_id: str,
    payload: schemas.ReviewReplyRequest,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.ReviewOut:
    review = db.get(models.Review, review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")

    listing = db.get(models.Listing, review.listing_id)
    if listing is None or listing.host_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the listing's host can reply to this review",
        )

    review.host_reply = payload.reply
    db.commit()
    db.refresh(review)
    return _to_review_out(review, db.get(models.User, review.author_id), listing.title)


@router.post("/{review_id}/flag", response_model=schemas.ReviewOut)
def flag_review(
    review_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.ReviewOut:
    review = db.get(models.Review, review_id)
    if review is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found")
    if review.author_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You can't report your own review")

    review.flagged = True
    db.commit()
    db.refresh(review)

    listing = db.get(models.Listing, review.listing_id)
    return _to_review_out(
        review, db.get(models.User, review.author_id), listing.title if listing is not None else "Listing"
    )
