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
