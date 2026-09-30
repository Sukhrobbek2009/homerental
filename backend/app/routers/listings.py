import logging
import secrets
from typing import Literal

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from .. import models, schemas, storage
from ..config import settings
from ..database import get_db
from ..deps import get_current_user, require_role

logger = logging.getLogger(__name__)

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
def list_active_listings(
    response: Response,
    type: models.ListingType | None = Query(default=None),
    city: str | None = Query(default=None, max_length=160),
    min_price: float | None = Query(default=None, ge=0),
    max_price: float | None = Query(default=None, ge=0),
    verified_only: bool = Query(default=False),
    sort: Literal["top_rated", "price"] | None = Query(default=None),
    page: int | None = Query(default=None, ge=1),
    page_size: int | None = Query(default=None, ge=1, le=100),
    db: Session = Depends(get_db),
) -> list[models.Listing]:
    query = db.query(models.Listing).filter(models.Listing.status == models.ListingStatus.active)

    if type is not None:
        query = query.filter(models.Listing.listing_type == type)
    if city:
        # Escape LIKE wildcards so "%" or "_" in the search match literally.
        term = city.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        query = query.filter(models.Listing.location.ilike(f"%{term}%", escape="\\"))
    if min_price is not None:
        query = query.filter(models.Listing.price >= min_price)
    if max_price is not None:
        query = query.filter(models.Listing.price <= max_price)
    if verified_only:
        query = query.filter(models.Listing.verified.is_(True))

    if sort == "price":
        query = query.order_by(models.Listing.price.asc())
    else:
        query = query.order_by(models.Listing.created_at.desc())

    listings = _attach_ratings(db, _attach_host_names(db, query.all()))

    if sort == "top_rated":
        listings.sort(
            key=lambda listing: (
                listing.rating_avg is None,
                -(listing.rating_avg or 0),
                -listing.review_count,
            )
        )

    response.headers["X-Total-Count"] = str(len(listings))

    if page is not None or page_size is not None:
        page = page or 1
        page_size = page_size or 20
        start = (page - 1) * page_size
        listings = listings[start : start + page_size]

    return listings


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
    current_user: models.User = Depends(require_role("host")),
    db: Session = Depends(get_db),
) -> models.Listing:
    listing = models.Listing(host_id=current_user.id, **payload.model_dump())
    db.add(listing)
    db.commit()
    db.refresh(listing)
    return _attach_rating(db, _attach_host_name(db, listing))


@router.put("/{listing_id}", response_model=schemas.ListingOut)
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
    photo_urls = list(listing.photos)
    db.delete(listing)
    db.commit()
    # The photos are publicly readable, so don't leave them behind. Best
    # effort: the listing is already gone, so a storage error only gets logged.
    for url in photo_urls:
        key = storage.key_from_url(url)
        if key is None:
            continue
        try:
            storage.delete(key)
        except (BotoCoreError, ClientError):
            logger.exception("Could not delete photo %s of deleted listing %s", key, listing_id)
    return schemas.ListingDeleteResult(deleted=True, message="Listing deleted.")


MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTOS_PER_LISTING = 8
# Headroom for the multipart boundary and part headers around the file.
_MULTIPART_OVERHEAD_BYTES = 64 * 1024


def _detect_image_type(data: bytes) -> tuple[str, str] | None:
    """Return (content_type, extension) from the file's magic bytes.

    The declared Content-Type and filename come from the client and can say
    anything, so only the bytes themselves decide what's accepted.
    """
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg", "jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png", "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return None


def _photo_limit_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=f"This listing already has the maximum of {MAX_PHOTOS_PER_LISTING} photos.",
    )


@router.post("/{listing_id}/photos", response_model=schemas.ListingOut, status_code=status.HTTP_201_CREATED)
def upload_listing_photo(
    listing_id: str,
    request: Request,
    photo: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.Listing:
    # Reject oversized requests up front when the client declares a length,
    # before reading anything more than we have to.
    declared_length = request.headers.get("content-length")
    if declared_length and declared_length.isdigit() and int(declared_length) > MAX_PHOTO_BYTES + _MULTIPART_OVERHEAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Photos must be under 5 MB.")

    listing = _get_owned_listing(listing_id, current_user, db)
    if len(listing.photos) >= MAX_PHOTOS_PER_LISTING:
        raise _photo_limit_error()

    if not settings.s3_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Photo uploads aren't configured on this server yet.",
        )

    data = photo.file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Photos must be under 5 MB.")
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The uploaded photo is empty.")

    detected = _detect_image_type(data)
    if detected is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Photos must be JPEG, PNG or WebP images.",
        )
    content_type, extension = detected

    # Random name; the uploaded filename is never used.
    key = f"listings/{listing.id}/{secrets.token_hex(16)}.{extension}"
    try:
        url = storage.upload(key, data, content_type)
    except (BotoCoreError, ClientError):
        logger.exception("Uploading listing photo %s failed", key)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not store the photo. Please try again.",
        )

    # Re-read the listing under a row lock so concurrent uploads can't push it
    # past the limit (FOR UPDATE on Postgres; SQLite serializes writes anyway).
    listing = (
        db.query(models.Listing)
        .filter(models.Listing.id == listing.id)
        .populate_existing()
        .with_for_update()
        .one()
    )
    if len(listing.photos) >= MAX_PHOTOS_PER_LISTING:
        db.rollback()
        try:
            storage.delete(key)
        except (BotoCoreError, ClientError):
            logger.exception("Could not delete orphaned listing photo %s", key)
        raise _photo_limit_error()

    listing.photos = [*listing.photos, url]
    if not listing.image_url:
        listing.image_url = url
    db.commit()
    db.refresh(listing)
    return _attach_rating(db, _attach_host_name(db, listing))
