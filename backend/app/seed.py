from datetime import date

from sqlalchemy.orm import Session

from . import models

# Owner of record for the starter listings below. Not a real signup — has no
# password hash, so it can't log in; it exists only so seeded listings have a
# valid host_id.
DEMO_HOST_EMAIL = "starter-host@uzbekrentals.app"

# Converted 1:1 from the first six listing cards on listings.html, keeping
# every field the Listing schema stores, including the display-only ones
# (rating, verified, guest_favorite) that back the card's star rating,
# "Verified" tag, and "Guest favorite" badge.
STARTER_LISTINGS = [
    dict(
        listing_type=models.ListingType.home,
        title="Sunlit loft near Prospect Park",
        location="Brooklyn, NY",
        price=145,
        price_unit="night",
        image_url="https://images.unsplash.com/photo-1568605114967-8130f3a36994?w=800&q=60",
        home_type="Entire apartment",
        rating=4.97,
        verified=True,
        guest_favorite=True,
    ),
    dict(
        listing_type=models.ListingType.home,
        title="Family house with backyard",
        location="Sacramento, CA",
        price=210,
        price_unit="night",
        image_url="https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=800&q=60",
        home_type="Entire house",
        rating=4.88,
        verified=True,
    ),
    dict(
        listing_type=models.ListingType.car,
        title="2021 Toyota Camry",
        location="Seattle, WA",
        price=52,
        price_unit="day",
        image_url="https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=800&q=60",
        vehicle_type="Sedan",
        transmission="Automatic",
        rating=4.95,
        verified=True,
        guest_favorite=True,
    ),
    dict(
        listing_type=models.ListingType.home,
        title="Modern studio downtown",
        location="Denver, CO",
        price=98,
        price_unit="night",
        image_url="https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=800&q=60",
        home_type="Entire studio",
        rating=4.90,
    ),
    dict(
        listing_type=models.ListingType.car,
        title="Honda CR-V, AWD",
        location="Chicago, IL",
        price=64,
        price_unit="day",
        image_url="https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=800&q=60",
        vehicle_type="SUV",
        transmission="Automatic",
        rating=4.82,
        verified=True,
    ),
    dict(
        listing_type=models.ListingType.home,
        title="Cozy 2BR near the park",
        location="Philadelphia, PA",
        price=132,
        price_unit="night",
        image_url="https://images.unsplash.com/photo-1583608205776-bfd35f0d9f83?w=800&q=60",
        home_type="Entire apartment",
        bedrooms=2,
        rating=4.91,
    ),
]


def seed_starter_listings(db: Session) -> None:
    """Keep the demo host's listings in sync with STARTER_LISTINGS.

    Re-runs on every startup and only ever touches rows owned by the demo
    host, so it stays safe to edit this list and see the change reflected
    without hand-editing the database — and never touches a real host's
    listings.
    """
    host = db.query(models.User).filter(models.User.email == DEMO_HOST_EMAIL).first()
    if host is None:
        host = models.User(
            full_name="Uzbek Rentals",
            email=DEMO_HOST_EMAIL,
            role=models.UserRole.host,
        )
        db.add(host)
        db.flush()

    db.query(models.Listing).filter(models.Listing.host_id == host.id).delete(synchronize_session=False)

    for data in STARTER_LISTINGS:
        db.add(models.Listing(host_id=host.id, status=models.ListingStatus.active, **data))

    db.commit()


# The listing-detail page's example reviews, authored for this task since no
# reviews UI or review content existed anywhere in the app before. Attached
# to one specific starter listing so the other five (and every car) exercise
# the "No reviews yet" empty state honestly, rather than everything having
# fake reviews.
DEMO_REVIEW_TARGET_TITLE = "Family house with backyard"
DEMO_REVIEWER_EMAIL_PREFIX = "demo-review-"

STARTER_REVIEWS = [
    dict(
        reviewer_name="Dilnoza K.",
        reviewer_email="demo-review-1@uzbekrentals.app",
        rating=5,
        comment=(
            "The backyard was perfect for our kids to run around, and the house was "
            "spotless. Definitely booking again next time we're in Sacramento."
        ),
        start_date=date(2026, 6, 1),
        end_date=date(2026, 6, 5),
        guest_count=4,
    ),
    dict(
        reviewer_name="Marcus T.",
        reviewer_email="demo-review-2@uzbekrentals.app",
        rating=5,
        comment=(
            "Great communication from the host and the place was exactly as described. "
            "Quiet street, comfortable beds, would recommend."
        ),
        start_date=date(2026, 5, 10),
        end_date=date(2026, 5, 13),
        guest_count=2,
    ),
    dict(
        reviewer_name="Aliya R.",
        reviewer_email="demo-review-3@uzbekrentals.app",
        rating=4,
        comment=(
            "Really nice house overall - spacious kitchen and a lovely yard. Parking "
            "was a little tight with two cars, but otherwise a great stay."
        ),
        start_date=date(2026, 4, 18),
        end_date=date(2026, 4, 21),
        guest_count=3,
    ),
]


def seed_starter_reviews(db: Session) -> None:
    """Keep STARTER_REVIEWS attached to DEMO_REVIEW_TARGET_TITLE in sync.

    Re-runs on every startup. Only ever touches the synthetic reviewer
    accounts (email prefix demo-review-) and the bookings/reviews they
    created, so it's safe to run repeatedly and never touches real users.
    Must run after seed_starter_listings, since it looks the listing up by
    title (starter listing ids are regenerated on every reseed).
    """
    listing = db.query(models.Listing).filter(models.Listing.title == DEMO_REVIEW_TARGET_TITLE).first()
    if listing is None:
        return

    old_reviewer_ids = [
        row.id
        for row in db.query(models.User).filter(models.User.email.like(f"{DEMO_REVIEWER_EMAIL_PREFIX}%")).all()
    ]
    if old_reviewer_ids:
        old_booking_ids = [
            row.id for row in db.query(models.Booking).filter(models.Booking.renter_id.in_(old_reviewer_ids)).all()
        ]
        if old_booking_ids:
            db.query(models.Review).filter(models.Review.booking_id.in_(old_booking_ids)).delete(
                synchronize_session=False
            )
            db.query(models.Booking).filter(models.Booking.id.in_(old_booking_ids)).delete(
                synchronize_session=False
            )
        db.query(models.User).filter(models.User.id.in_(old_reviewer_ids)).delete(synchronize_session=False)
    db.flush()

    for data in STARTER_REVIEWS:
        reviewer = models.User(
            full_name=data["reviewer_name"],
            email=data["reviewer_email"],
            role=models.UserRole.renter,
        )
        db.add(reviewer)
        db.flush()

        nights = (data["end_date"] - data["start_date"]).days
        booking = models.Booking(
            listing_id=listing.id,
            renter_id=reviewer.id,
            host_id=listing.host_id,
            start_date=data["start_date"],
            end_date=data["end_date"],
            guest_count=data["guest_count"],
            total_price=round(listing.price * nights, 2),
            status=models.BookingStatus.completed,
        )
        db.add(booking)
        db.flush()

        db.add(
            models.Review(
                booking_id=booking.id,
                listing_id=listing.id,
                author_id=reviewer.id,
                rating=data["rating"],
                comment=data["comment"],
            )
        )

    db.commit()
