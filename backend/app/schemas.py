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
    image_url: str | None = Field(default=None, max_length=500)
    bedrooms: int | None = Field(default=None, ge=0, le=50)
    home_type: str | None = Field(default=None, max_length=60)
    vehicle_type: str | None = Field(default=None, max_length=60)
    transmission: str | None = Field(default=None, max_length=30)

    @field_validator("title", "location")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class ListingCreate(ListingBase):
    status: ListingStatus = ListingStatus.active


class ListingUpdate(BaseModel):
    listing_type: ListingType | None = None
    title: str | None = Field(default=None, min_length=3, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    location: str | None = Field(default=None, min_length=2, max_length=160)
    price: float | None = Field(default=None, gt=0, le=1_000_000)
    price_unit: Literal["night", "day"] | None = None
    image_url: str | None = Field(default=None, max_length=500)
    status: ListingStatus | None = None
    bedrooms: int | None = Field(default=None, ge=0, le=50)
    home_type: str | None = Field(default=None, max_length=60)
    vehicle_type: str | None = Field(default=None, max_length=60)
    transmission: str | None = Field(default=None, max_length=30)


class ListingOut(ListingBase):
    id: str
    host_id: str
    status: ListingStatus
    rating: float | None
    verified: bool
    guest_favorite: bool
    created_at: datetime

    model_config = {"from_attributes": True}


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

    model_config = {"from_attributes": True}


class ReviewCreate(BaseModel):
    booking_id: str
    rating: int = Field(ge=1, le=5)
    comment: str | None = Field(default=None, max_length=2000)


class ReviewOut(BaseModel):
    id: str
    booking_id: str
    listing_id: str
    author_id: str
    rating: int
    comment: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
