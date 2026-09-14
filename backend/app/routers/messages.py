from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .. import models, schemas
from ..database import get_db
from ..deps import get_current_user

router = APIRouter(prefix="/api/messages", tags=["messages"])


def thread_id_for(listing_id: str, renter_id: str) -> str:
    return f"{listing_id}:{renter_id}"


def _listing_id_from_thread(thread_id: str) -> str:
    return thread_id.split(":", 1)[0]


def _other_party(message: models.Message, current_user_id: str) -> str:
    return message.to_id if message.from_id == current_user_id else message.from_id


def _get_thread_messages(thread_id: str, current_user: models.User, db: Session) -> list[models.Message]:
    messages = (
        db.query(models.Message)
        .filter(models.Message.thread_id == thread_id)
        .order_by(models.Message.created_at.asc())
        .all()
    )
    if not messages or not any(
        m.from_id == current_user.id or m.to_id == current_user.id for m in messages
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thread not found")
    return messages


@router.post("", response_model=schemas.MessageOut, status_code=status.HTTP_201_CREATED)
def contact_host(
    payload: schemas.MessageCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.Message:
    listing = db.get(models.Listing, payload.listing_id)
    if listing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Listing not found")
    if listing.host_id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You can't message yourself about your own listing",
        )

    message = models.Message(
        thread_id=thread_id_for(listing.id, current_user.id),
        from_id=current_user.id,
        to_id=listing.host_id,
        body=payload.body,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.get("/threads", response_model=list[schemas.ThreadOut])
def list_my_threads(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[schemas.ThreadOut]:
    all_messages = (
        db.query(models.Message)
        .filter(or_(models.Message.from_id == current_user.id, models.Message.to_id == current_user.id))
        .order_by(models.Message.created_at.asc())
        .all()
    )

    grouped: dict[str, list[models.Message]] = {}
    for message in all_messages:
        grouped.setdefault(message.thread_id, []).append(message)

    listing_ids = {_listing_id_from_thread(tid) for tid in grouped}
    listings = {
        listing.id: listing
        for listing in db.query(models.Listing).filter(models.Listing.id.in_(listing_ids)).all()
    }

    other_ids = {_other_party(msgs[-1], current_user.id) for msgs in grouped.values()}
    names = {u.id: u.full_name for u in db.query(models.User).filter(models.User.id.in_(other_ids)).all()}

    threads: list[schemas.ThreadOut] = []
    for thread_id, msgs in grouped.items():
        last = msgs[-1]
        other_id = _other_party(last, current_user.id)
        listing = listings.get(_listing_id_from_thread(thread_id))
        threads.append(
            schemas.ThreadOut(
                thread_id=thread_id,
                listing_id=listing.id if listing else _listing_id_from_thread(thread_id),
                listing_title=listing.title if listing else "Listing",
                listing_type=listing.listing_type if listing else models.ListingType.home,
                other_user_id=other_id,
                other_user_name=names.get(other_id, "User"),
                last_message=last.body,
                last_message_at=last.created_at,
                unread=any(m.to_id == current_user.id and not m.read for m in msgs),
            )
        )

    threads.sort(key=lambda t: t.last_message_at, reverse=True)
    return threads


@router.get("/threads/{thread_id}", response_model=schemas.ThreadDetailOut)
def get_thread(
    thread_id: str,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> schemas.ThreadDetailOut:
    messages = _get_thread_messages(thread_id, current_user, db)

    unread_ids = [m.id for m in messages if m.to_id == current_user.id and not m.read]
    if unread_ids:
        db.query(models.Message).filter(models.Message.id.in_(unread_ids)).update(
            {models.Message.read: True}, synchronize_session=False
        )
        db.commit()
        for m in messages:
            if m.id in unread_ids:
                m.read = True

    last = messages[-1]
    other_id = _other_party(last, current_user.id)
    other_user = db.get(models.User, other_id)
    listing = db.get(models.Listing, _listing_id_from_thread(thread_id))

    return schemas.ThreadDetailOut(
        thread_id=thread_id,
        listing_id=listing.id if listing else _listing_id_from_thread(thread_id),
        listing_title=listing.title if listing else "Listing",
        listing_type=listing.listing_type if listing else models.ListingType.home,
        other_user_id=other_id,
        other_user_name=other_user.full_name if other_user else "User",
        messages=messages,
    )


@router.post("/threads/{thread_id}/reply", response_model=schemas.MessageOut, status_code=status.HTTP_201_CREATED)
def reply_in_thread(
    thread_id: str,
    payload: schemas.MessageReply,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> models.Message:
    messages = _get_thread_messages(thread_id, current_user, db)
    other_id = _other_party(messages[-1], current_user.id)

    message = models.Message(
        thread_id=thread_id,
        from_id=current_user.id,
        to_id=other_id,
        body=payload.body,
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message
