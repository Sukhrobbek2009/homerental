from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/listings", tags=["listings"])


def _get_owned_listing(listing_id: str, current_user: models.User, db: Session) -> models.Listing:
    listing = db.get(models.Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    if listing.host_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only change your own listings.")
    return listing


def _attach_host_name(db: Session, listing: models.Listing) -> models.Listing:
    host = db.get(models.User, listing.host_id)
    listing.host_name = host.full_name if host is not None else "Host"
    listing.host_verified = host.verified if host is not None else False
    return listing


def _attach_host_names(db: Session, listings: list[models.Listing]) -> list[models.Listing]:
    host_ids = {listing.host_id for listing in listings}
    hosts_by_id = {}
    if host_ids:
        hosts = db.query(models.User).filter(models.User.id.in_(host_ids)).all()
        hosts_by_id = {host.id: host for host in hosts}
    for listing in listings:
        host = hosts_by_id.get(listing.host_id)
        listing.host_name = host.full_name if host is not None else "Host"
        listing.host_verified = host.verified if host is not None else False
    return listings


def _attach_ratings(db: Session, listings: list[models.Listing]) -> list[models.Listing]:
    listing_ids = {listing.id for listing in listings}
    stats: dict[str, tuple[float, int]] = {}
    if listing_ids:
        rows = (
            db.query(models.Review.listing_id, func.avg(models.Review.rating), func.count(models.Review.id))
            .filter(models.Review.listing_id.in_(listing_ids), models.Review.flagged.is_(False))
            .group_by(models.Review.listing_id)
            .all()
        )
        stats = {listing_id: (avg_rating, count) for listing_id, avg_rating, count in rows}
    for listing in listings:
        avg_rating, count = stats.get(listing.id, (None, 0))
        listing.rating_avg = round(avg_rating, 2) if avg_rating is not None else None
        listing.review_count = count
    return listings


def _attach_rating(db: Session, listing: models.Listing) -> models.Listing:
    return _attach_ratings(db, [listing])[0]


@router.get("", response_model=list[schemas.ListingOut])
def list_active_listings(db: Session = Depends(get_db)) -> list[models.Listing]:
    listings = (
        db.query(models.Listing)
        .filter(models.Listing.status == models.ListingStatus.active)
        .order_by(models.Listing.created_at.desc())
        .all()
    )
    return _attach_ratings(db, _attach_host_names(db, listings))


@router.get("/mine", response_model=list[schemas.ListingOut])
def list_my_listings(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[models.Listing]:
    listings = (
        db.query(models.Listing)
        .filter(models.Listing.host_id == current_user.id)
        .order_by(models.Listing.created_at.desc())
        .all()
    )
    return _attach_ratings(db, _attach_host_names(db, listings))


@router.get("/{listing_id}", response_model=schemas.ListingOut)
def get_listing(listing_id: str, db: Session = Depends(get_db)) -> models.Listing:
    listing = db.get(models.Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    return _attach_rating(db, _attach_host_name(db, listing))


@router.get("/{listing_id}/booked-ranges", response_model=list[schemas.BookedRangeOut])
def get_listing_booked_ranges(listing_id: str, db: Session = Depends(get_db)) -> list[models.Booking]:
    listing = db.get(models.Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    return (
        db.query(models.Booking)
        .filter(
            models.Booking.listing_id == listing_id,
            models.Booking.status.in_([models.BookingStatus.pending, models.BookingStatus.confirmed]),
        )
        .order_by(models.Booking.start_date)
        .all()
    )


@router.post("", response_model=schemas.ListingOut, status_code=status.HTTP_201_CREATED)
def create_listing(
    payload: schemas.ListingCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.Listing:
    listing = models.Listing(host_id=current_user.id, **payload.model_dump())
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return _attach_rating(db, _attach_host_name(db, listing))


@router.patch("/{listing_id}", response_model=schemas.ListingOut)
def update_listing(
    listing_id: str,
    payload: schemas.ListingUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.Listing:
    listing = _get_owned_listing(listing_id, current_user, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(listing, field, value)
    db.commit()
    db.refresh(listing)
    return _attach_rating(db, _attach_host_name(db, listing))


@router.delete("/{listing_id}", response_model=schemas.ListingDeleteResult)
def delete_listing(
    listing_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.ListingDeleteResult:
    listing = _get_owned_listing(listing_id, current_user, db)
    has_bookings = (
        db.query(models.Booking).filter(models.Booking.listing_id == listing.id).first() is not None
    )
    if has_bookings:
        listing.status = models.ListingStatus.paused
        db.commit()
        db.refresh(listing)
        return schemas.ListingDeleteResult(
            deleted=False,
            message=(
                "This listing has existing bookings, so it can't be deleted. "
                "It has been marked as unavailable instead."
            ),
            listing=schemas.ListingOut.model_validate(_attach_rating(db, _attach_host_name(db, listing))),
        )
    db.delete(listing)
    db.commit()
    return schemas.ListingDeleteResult(deleted=True, message="Listing deleted.")
