import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

from .models import BookingStatus, ListingStatus, ListingType, UserRole

PHONE_RE = re.compile(r"^\+?[0-9\s\-()]{7,20}$")


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    phone: str | None = Field(default=None)
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.renter

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        if value is None or value.strip() == "":
            return None
        if not PHONE_RE.match(value.strip()):
            raise ValueError("Enter a valid phone number")
        return value.strip()

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        if not re.search(r"[A-Za-z]", value) or not re.search(r"[0-9]", value):
            raise ValueError("Password must contain at least one letter and one number")
        return value

    @field_validator("full_name")
    @classmethod
    def validate_full_name(cls, value: str) -> str:
        return value.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthRequest(BaseModel):
    credential: str = Field(min_length=1)


class RoleUpdateRequest(BaseModel):
    role: UserRole


class UserOut(BaseModel):
    id: str
    full_name: str
    email: EmailStr
    phone: str | None
    role: UserRole

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserOut


class RefreshRequest(BaseModel):
    refresh_token: str


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ListingBase(BaseModel):
    listing_type: ListingType
    title: str = Field(min_length=3, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    location: str = Field(min_length=2, max_length=160)
    price: float = Field(gt=0, le=1_000_000)
    price_unit: Literal["night", "day"]
    image_url: str | None = Field(default=None, max_length=3_000_000)
    amenities: str | None = Field(default=None, max_length=1000)
    bedrooms: int | None = Field(default=None, ge=0, le=50)
    home_type: str | None = Field(default=None, max_length=60)
    vehicle_type: str | None = Field(default=None, max_length=60)
    transmission: str | None = Field(default=None, max_length=30)
    available_from: date | None = Field(default=None)
    available_to: date | None = Field(default=None)

    @field_validator("title", "location")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("amenities")
    @classmethod
    def strip_amenities(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None

    @field_validator("available_to")
    @classmethod
    def available_to_after_from(cls, value: date | None, info) -> date | None:
        start = info.data.get("available_from")
        if value is not None and start is not None and value <= start:
            raise ValueError("Available-to date must be after the available-from date")
        return value


class ListingCreate(ListingBase):
    status: ListingStatus = ListingStatus.active


class ListingUpdate(BaseModel):
    listing_type: ListingType | None = None
    title: str | None = Field(default=None, min_length=3, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, min_length=2, max_length=160)
    price: float | None = Field(default=None, gt=0, le=1_000_000)
    price_unit: Literal["night", "day"] | None = None
    image_url: str | None = Field(default=None, max_length=3_000_000)
    amenities: str | None = Field(default=None, max_length=1000)
    status: ListingStatus | None = None
    bedrooms: int | None = Field(default=None, ge=0, le=50)
    home_type: str | None = Field(default=None, max_length=60)
    vehicle_type: str | None = Field(default=None, max_length=60)
    transmission: str | None = Field(default=None, max_length=30)
    available_from: date | None = Field(default=None)
    available_to: date | None = Field(default=None)

    @field_validator("available_to")
    @classmethod
    def available_to_after_from(cls, value: date | None, info) -> date | None:
        start = info.data.get("available_from")
        if value is not None and start is not None and value <= start:
            raise ValueError("Available-to date must be after the available-from date")
        return value


class ListingOut(ListingBase):
    id: str
    host_id: str
    host_name: str = "Host"
    status: ListingStatus
    rating: float | None
    verified: bool
    guest_favorite: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class ListingDeleteResult(BaseModel):
    deleted: bool
    message: str
    listing: ListingOut | None = None


class BookedRangeOut(BaseModel):
    start_date: date
    end_date: date


class BookingCreate(BaseModel):
    listing_id: str
    start_date: date
    end_date: date
    guest_count: int = Field(default=1, ge=1, le=50)

    @field_validator("end_date")
    @classmethod
    def end_after_start(cls, value: date, info) -> date:
        start = info.data.get("start_date")
        if start is not None and value <= start:
            raise ValueError("End date must be after start date")
        return value


class BookingStatusUpdate(BaseModel):
    status: BookingStatus


class BookingOut(BaseModel):
    id: str
    listing_id: str
    renter_id: str
    host_id: str
    start_date: date
    end_date: date
    guest_count: int
    total_price: float
    status: BookingStatus
    created_at: datetime
    listing_title: str = "Listing"
    listing_location: str = ""
    listing_image_url: str | None = None
    listing_type: ListingType = ListingType.home
    listing_price_unit: str = "night"
    renter_name: str = "Guest"
    host_name: str = "Host"

    model_config = {"from_attributes": True}


class MessageCreate(BaseModel):
    listing_id: str
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message can't be empty")
        return value


class MessageOut(BaseModel):
    id: str
    thread_id: str
    from_id: str
    to_id: str
    body: str
    read: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class MessageReply(BaseModel):
    body: str = Field(min_length=1, max_length=2000)

    @field_validator("body")
    @classmethod
    def strip_body(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message can't be empty")
        return value


class ThreadOut(BaseModel):
    thread_id: str
    listing_id: str
    listing_title: str = "Listing"
    listing_type: ListingType = ListingType.home
    other_user_id: str
    other_user_name: str = "User"
    last_message: str
    last_message_at: datetime
    unread: bool


class ThreadDetailOut(BaseModel):
    thread_id: str
    listing_id: str
    listing_title: str = "Listing"
    listing_type: ListingType = ListingType.home
    other_user_id: str
    other_user_name: str = "User"
    messages: list[MessageOut]


class ReviewCreate(BaseModel):
    booking_id: str
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewOut(BaseModel):
    id: str
    booking_id: str
    listing_id: str
    author_id: str
    author_name: str
    rating: int
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
