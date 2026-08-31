from fastapi import APIRouter, Depends, HTTPException, status
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this listing")
    return listing


@router.get("/mine", response_model=list[schemas.ListingOut])
def list_my_listings(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[models.Listing]:
    return (
        db.query(models.Listing)
        .filter(models.Listing.host_id == current_user.id)
        .order_by(models.Listing.created_at.desc())
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
    return listing


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
    return listing


@router.delete("/{listing_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_listing(
    listing_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    listing = _get_owned_listing(listing_id, current_user, db)
    db.delete(listing)
    db.commit()
