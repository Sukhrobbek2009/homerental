from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/bookings", tags=["bookings"])


def _get_accessible_booking(booking_id: str, current_user: models.User, db: Session) -> models.Booking:
    booking = db.get(models.Booking, booking_id)
    if booking is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Booking not found")
    if current_user.id not in (booking.renter_id, booking.host_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this booking")
    return booking


@router.get("/mine", response_model=list[schemas.BookingOut])
def list_my_bookings(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[models.Booking]:
    return (
        db.query(models.Booking)
        .filter(models.Booking.renter_id == current_user.id)
        .order_by(models.Booking.created_at.desc())
        .all()
    )


@router.get("/hosting", response_model=list[schemas.BookingOut])
def list_bookings_for_my_listings(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[models.Booking]:
    return (
        db.query(models.Booking)
        .filter(models.Booking.host_id == current_user.id)
        .order_by(models.Booking.created_at.desc())
        .all()
    )


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

    nights = (payload.end_date - payload.start_date).days
    booking = models.Booking(
        listing_id=listing.id,
        renter_id=current_user.id,
        host_id=listing.host_id,
        start_date=payload.start_date,
        end_date=payload.end_date,
        guest_count=payload.guest_count,
        total_price=round(listing.price * nights, 2),
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


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
    return booking
