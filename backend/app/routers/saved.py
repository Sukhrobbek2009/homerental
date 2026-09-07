from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user
from .listings import _attach_host_names

router = APIRouter(prefix="/api/saved", tags=["saved"])


@router.get("", response_model=list[schemas.ListingOut])
def list_saved_listings(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[models.Listing]:
    saved = (
        db.query(models.SavedListing)
        .filter(models.SavedListing.user_id == current_user.id)
        .order_by(models.SavedListing.created_at.desc())
        .all()
    )
    listing_ids = [row.listing_id for row in saved]
    if not listing_ids:
        return []
    by_id = {
        listing.id: listing
        for listing in db.query(models.Listing).filter(models.Listing.id.in_(listing_ids)).all()
    }
    ordered = [by_id[lid] for lid in listing_ids if lid in by_id]
    return _attach_host_names(db, ordered)


@router.get("/ids", response_model=list[str])
def list_saved_listing_ids(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[str]:
    rows = (
        db.query(models.SavedListing.listing_id)
        .filter(models.SavedListing.user_id == current_user.id)
        .all()
    )
    return [row[0] for row in rows]


@router.post("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
def save_listing(
    listing_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    listing = db.get(models.Listing, listing_id)
    if listing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    exists = (
        db.query(models.SavedListing)
        .filter(models.SavedListing.user_id == current_user.id, models.SavedListing.listing_id == listing_id)
        .first()
    )
    if exists is not None:
        return
    db.add(models.SavedListing(user_id=current_user.id, listing_id=listing_id))
    db.commit()


@router.delete("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
def unsave_listing(
    listing_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    row = (
        db.query(models.SavedListing)
        .filter(models.SavedListing.user_id == current_user.id, models.SavedListing.listing_id == listing_id)
        .first()
    )
    if row is not None:
        db.delete(row)
        db.commit()
