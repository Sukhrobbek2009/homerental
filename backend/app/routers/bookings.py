from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

DATES_TAKEN_MESSAGE = "Those dates are no longer available for this listing. Please choose different dates."

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


def _get_accessible_booking(booking_id: str, current_user: models.User, db: Session) -> models.Booking:
    booking = db.get(models.Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    if current_user.id not in (booking.renter_id, booking.host_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this booking")
    return booking


def _attach_booking_extras(db: Session, bookings: list[models.Booking]) -> list[models.Booking]:
    listing_ids = {b.listing_id for b in bookings}
    listings = {}
    if listing_ids:
        listings = {l.id: l for l in db.query(models.Listing).filter(models.Listing.id.in_(listing_ids)).all()}

    user_ids = {b.renter_id for b in bookings} | {b.host_id for b in bookings}
    names = {}
    if user_ids:
        names = {u.id: u.full_name for u in db.query(models.User).filter(models.User.id.in_(user_ids)).all()}

    for booking in bookings:
        listing = listings.get(booking.listing_id)
        booking.listing_title = listing.title if listing is not None else "Listing"
        booking.listing_location = listing.location if listing is not None else ""
        booking.listing_image_url = listing.image_url if listing is not None else None
        booking.listing_type = listing.listing_type if listing is not None else models.ListingType.home
        booking.listing_price_unit = listing.price_unit if listing is not None else "night"
        booking.renter_name = names.get(booking.renter_id, "Guest")
        booking.host_name = names.get(booking.host_id, "Host")
    return bookings


@router.get("/mine", response_model=list[schemas.BookingOut])
def list_my_bookings(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[models.Booking]:
    bookings = (
        db.query(models.Booking)
        .filter(models.Booking.renter_id == current_user.id)
        .order_by(models.Booking.created_at.desc())
        .all()
    )
    return _attach_booking_extras(db, bookings)


@router.get("/hosting", response_model=list[schemas.BookingOut])
def list_bookings_for_my_listings(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[models.Booking]:
    bookings = (
        db.query(models.Booking)
        .filter(models.Booking.host_id == current_user.id)
        .order_by(models.Booking.created_at.desc())
        .all()
    )
    return _attach_booking_extras(db, bookings)


@router.post("", response_model=schemas.BookingOut, status_code=status.HTTP_201_CREATED)
def create_booking(
    payload: schemas.BookingCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.Booking:
    listing = db.get(models.Listing, payload.listing_id)
    if listing is None or listing.status != models.ListingStatus.active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    if listing.host_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You can't book your own listing")

    if listing.available_from is not None and payload.start_date < listing.available_from:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This listing isn't available before {listing.available_from.isoformat()}",
        )
    if listing.available_to is not None and payload.end_date > listing.available_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"This listing isn't available after {listing.available_to.isoformat()}",
        )

    def _overlap_filters(*, statuses: list[models.BookingStatus], exclude_id: str | None = None):
        filters = [
            models.Booking.listing_id == listing.id,
            models.Booking.status.in_(statuses),
            models.Booking.start_date < payload.end_date,
            models.Booking.end_date > payload.start_date,
        ]
        if exclude_id is not None:
            filters.append(models.Booking.id != exclude_id)
        return filters

    active_statuses = [models.BookingStatus.pending, models.BookingStatus.confirmed]
    overlapping = db.query(models.Booking).filter(*_overlap_filters(statuses=active_statuses)).first()
    if overlapping is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DATES_TAKEN_MESSAGE)

    nights = (payload.end_date - payload.start_date).days
    booking = models.Booking(
        listing_id=listing.id,
        renter_id=current_user.id,
        host_id=listing.host_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        guest_count=payload.guest_count,
        total_price=round(listing.price * nights, 2),
        status=models.BookingStatus.confirmed,
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    # A concurrent request may have booked the same dates in the gap between our
    # check and our insert above. Re-check now that we're committed, and if another
    # booking beat us to it, cancel the one we just made instead of leaving two
    # confirmed bookings for the same dates. Priority goes to whichever booking was
    # created first, tie-broken by id so exactly one of the two ever wins.
    beat_us_to_it = (
        db.query(models.Booking)
        .filter(
            *_overlap_filters(statuses=[models.BookingStatus.confirmed], exclude_id=booking.id),
            or_(
                models.Booking.created_at < booking.created_at,
                and_(models.Booking.created_at == booking.created_at, models.Booking.id < booking.id),
            ),
        )
        .first()
    )
    if beat_us_to_it is not None:
        booking.status = models.BookingStatus.cancelled
        db.commit()
        db.refresh(booking)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=DATES_TAKEN_MESSAGE)

    return _attach_booking_extras(db, [booking])[0]


@router.patch("/{booking_id}/status", response_model=schemas.BookingOut)
def update_booking_status(
    booking_id: str,
    payload: schemas.BookingStatusUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.Booking:
    booking = _get_accessible_booking(booking_id, current_user, db)
    booking.status = payload.status
    db.commit()
    db.refresh(booking)
    return _attach_booking_extras(db, [booking])[0]
