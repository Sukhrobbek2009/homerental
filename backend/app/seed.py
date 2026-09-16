import secrets
from datetime import date

from sqlalchemy.orm import Session

from . import models
from .config import settings
from .security import hash_password

# Demo-only admin account, seeded so there's a way into /admin without a
# self-service admin signup path (which would be a privilege-escalation
# hole). The password comes from DEMO_ADMIN_PASSWORD in the environment; if
# unset, a random one is generated and printed once so no fixed credential
# ever lives in source control.
DEMO_ADMIN_EMAIL = "admin@uzbekrentals.app"

# Stock photos reused across the starter listings below. Picked (and
# HTTP-checked) for matching the listing they're attached to — a plain sedan
# photo for every sedan-type car, a matching SUV photo for every SUV-type
# car, and a distinct interior/exterior shot for every home so the grid
# doesn't look obviously duplicated.
IMG_HOUSE_BACKYARD = "https://images.unsplash.com/photo-1512917774080-9991f1c4c750?w=800&q=60"
IMG_HOUSE_VICTORIAN = "https://images.unsplash.com/photo-1570129477492-45c003edd2be?w=800&q=60"
IMG_LIVING_ROOM_MODERN = "https://images.unsplash.com/photo-1493809842364-78817add7ffb?w=800&q=60"
IMG_LOFT = "https://images.unsplash.com/photo-1568605114967-8130f3a36994?w=800&q=60"
IMG_STUDIO = "https://images.unsplash.com/photo-1600596542815-ffad4c1539a9?w=800&q=60"
IMG_APARTMENT = "https://images.unsplash.com/photo-1583608205776-bfd35f0d9f83?w=800&q=60"
IMG_SEDAN = "https://images.unsplash.com/photo-1503376780353-7e6692767b70?w=800&q=60"
IMG_SUV = "https://images.unsplash.com/photo-1494976388531-d1058494cdd8?w=800&q=60"
IMG_SUV_WHITE = "https://images.unsplash.com/photo-1533473359331-0135ef1b58bf?w=800&q=60"

# Six starter hosts, each a plausible member of the Uzbek-American
# communities the app serves (Sacramento, Seattle, and Brooklyn all have
# sizable Uzbek/Bukharian populations; Philadelphia's is smaller but
# growing). A password is only ever set the first time an account is
# created — see _seed_user below — so re-seeding never disturbs a login
# that's already in use.
SEED_HOSTS = [
    dict(key="aziza", full_name="Aziza Yusupova", email="host-aziza@uzbekrentals.app", verified=True),
    dict(key="rustam", full_name="Rustam Nazarov", email="host-rustam@uzbekrentals.app", verified=False),
    dict(key="elyor", full_name="Elyor Karimov", email="host-elyor@uzbekrentals.app", verified=True),
    dict(key="sardor", full_name="Sardor Tashkentov", email="host-sardor@uzbekrentals.app", verified=False),
    dict(key="dilshod", full_name="Dilshod Rakhimov", email="host-dilshod@uzbekrentals.app", verified=True),
    dict(key="nodira", full_name="Nodira Abdullayeva", email="host-nodira@uzbekrentals.app", verified=False),
]

# Six starter renters who leave the reviews below. A mix of Uzbek and
# non-Uzbek names, same as any real marketplace serving a specific community
# alongside its wider neighborhood.
SEED_RENTERS = [
    dict(key="dilnoza", full_name="Dilnoza Karimova", email="renter-dilnoza@uzbekrentals.app"),
    dict(key="marcus", full_name="Marcus Thompson", email="renter-marcus@uzbekrentals.app"),
    dict(key="aliya", full_name="Aliya Rashidova", email="renter-aliya@uzbekrentals.app"),
    dict(key="javlon", full_name="Javlon Yusupov", email="renter-javlon@uzbekrentals.app"),
    dict(key="sarah", full_name="Sarah Chen", email="renter-sarah@uzbekrentals.app"),
    dict(key="farrukh", full_name="Farrukh Tillayev", email="renter-farrukh@uzbekrentals.app"),
]

# Twelve listings — three homes and three cars in each of Sacramento,
# Seattle, Brooklyn, and Philadelphia — split across the six hosts above.
STARTER_LISTINGS = [
    # Sacramento, CA — Aziza (2), Rustam (1)
    dict(
        host_key="aziza",
        listing_type=models.ListingType.home,
        title="Family house with backyard",
        description=(
            "A spacious 3-bedroom house on a quiet cul-de-sac, ten minutes from downtown. "
            "The fenced backyard is great for kids and weekend barbecues, and the kitchen "
            "is fully stocked for home cooking. A short drive to Central Asian grocery "
            "stores and a few favorite plov spots."
        ),
        location="Sacramento, CA",
        price=210,
        price_unit="night",
        image_url=IMG_HOUSE_BACKYARD,
        home_type="Entire house",
        bedrooms=3,
        verified=True,
    ),
    dict(
        host_key="aziza",
        listing_type=models.ListingType.car,
        title="2018 Toyota Corolla",
        description=(
            "A dependable, fuel-efficient sedan, recently serviced and detailed before "
            "every trip. Great for errands around town or a weekend drive out to Tahoe. "
            "Pickup available near downtown Sacramento."
        ),
        location="Sacramento, CA",
        price=45,
        price_unit="day",
        image_url=IMG_SEDAN,
        vehicle_type="Sedan",
        transmission="Automatic",
    ),
    dict(
        host_key="rustam",
        listing_type=models.ListingType.home,
        title="Spacious 4BR near Sac State",
        description=(
            "Plenty of room for extended family or a big group, with four bedrooms, two "
            "full baths, and a dining table that seats ten. Walking distance to Sac State "
            "and a short drive to the farmers market."
        ),
        location="Sacramento, CA",
        price=245,
        price_unit="night",
        image_url=IMG_HOUSE_VICTORIAN,
        home_type="Entire house",
        bedrooms=4,
    ),
    # Seattle, WA — Elyor (2), Sardor (1)
    dict(
        host_key="elyor",
        listing_type=models.ListingType.car,
        title="2021 Toyota Camry",
        description=(
            "Smooth, quiet ride with Apple CarPlay and adaptive cruise control — great "
            "for longer trips around the Puget Sound. Clean inside and out, with a full "
            "tank at pickup."
        ),
        location="Seattle, WA",
        price=52,
        price_unit="day",
        image_url=IMG_SEDAN,
        vehicle_type="Sedan",
        transmission="Automatic",
        verified=True,
        guest_favorite=True,
    ),
    dict(
        host_key="elyor",
        listing_type=models.ListingType.car,
        title="Honda CR-V, AWD",
        description=(
            "All-wheel drive SUV that handles Seattle's hills and weather with ease. "
            "Roomy trunk for luggage or grocery runs, and comfortable for longer drives "
            "out to the mountains."
        ),
        location="Seattle, WA",
        price=64,
        price_unit="day",
        image_url=IMG_SUV,
        vehicle_type="SUV",
        transmission="Automatic",
        verified=True,
    ),
    dict(
        host_key="sardor",
        listing_type=models.ListingType.home,
        title="Modern 1BR near Green Lake",
        description=(
            "A bright, newly renovated one-bedroom a few blocks from Green Lake. "
            "Walkable to cafes and a weekend farmers market, with an easy bus ride to "
            "the U District, where several Central Asian restaurants and markets are "
            "within reach."
        ),
        location="Seattle, WA",
        price=138,
        price_unit="night",
        image_url=IMG_LIVING_ROOM_MODERN,
        home_type="Entire apartment",
        bedrooms=1,
    ),
    # Brooklyn, NY — Dilshod (3)
    dict(
        host_key="dilshod",
        listing_type=models.ListingType.home,
        title="Sunlit loft near Prospect Park",
        description=(
            "An airy, sunlit loft with exposed brick, five minutes from Prospect Park. "
            "The neighborhood has a growing Uzbek and Central Asian community, with a "
            "few excellent bakeries and restaurants nearby. Quiet block, easy subway "
            "access."
        ),
        location="Brooklyn, NY",
        price=145,
        price_unit="night",
        image_url=IMG_LOFT,
        home_type="Entire apartment",
        verified=True,
        guest_favorite=True,
    ),
    dict(
        host_key="dilshod",
        listing_type=models.ListingType.car,
        title="2020 Honda Accord",
        description=(
            "Comfortable midsize sedan, great for getting around the city or a weekend "
            "trip upstate. Recently detailed, non-smoking, with plenty of trunk space."
        ),
        location="Brooklyn, NY",
        price=58,
        price_unit="day",
        image_url=IMG_SEDAN,
        vehicle_type="Sedan",
        transmission="Automatic",
    ),
    dict(
        host_key="dilshod",
        listing_type=models.ListingType.home,
        title="Bright studio near Sheepshead Bay",
        description=(
            "A cozy, freshly renovated studio in Sheepshead Bay, home to one of the "
            "city's largest Uzbek and Bukharian communities. Steps from the waterfront "
            "and an easy walk to halal markets and Central Asian restaurants along the "
            "avenue."
        ),
        location="Brooklyn, NY",
        price=99,
        price_unit="night",
        image_url=IMG_STUDIO,
        home_type="Entire studio",
    ),
    # Philadelphia, PA — Nodira (3)
    dict(
        host_key="nodira",
        listing_type=models.ListingType.home,
        title="Cozy 2BR near the park",
        description=(
            "A comfortable two-bedroom apartment a short walk from the park, with a "
            "full kitchen and in-unit laundry. Quiet residential block, close to public "
            "transit into Center City."
        ),
        location="Philadelphia, PA",
        price=132,
        price_unit="night",
        image_url=IMG_APARTMENT,
        home_type="Entire apartment",
        bedrooms=2,
    ),
    dict(
        host_key="nodira",
        listing_type=models.ListingType.car,
        title="2019 Toyota RAV4",
        description=(
            "Reliable compact SUV, great for city driving or a weekend trip to the "
            "Poconos. All-wheel drive, recently inspected, with a car seat available on "
            "request."
        ),
        location="Philadelphia, PA",
        price=55,
        price_unit="day",
        image_url=IMG_SUV,
        vehicle_type="SUV",
        transmission="Automatic",
    ),
    dict(
        host_key="nodira",
        listing_type=models.ListingType.car,
        title="2017 Subaru Outback",
        description=(
            "Spacious and dependable, this Outback is great for road trips or hauling "
            "gear. All-wheel drive handles Philly winters without issue."
        ),
        location="Philadelphia, PA",
        price=58,
        price_unit="day",
        image_url=IMG_SUV_WHITE,
        vehicle_type="SUV",
        transmission="Automatic",
    ),
]

# A handful of reviews spread across four of the twelve listings, each tied
# to a plausible completed booking by one of SEED_RENTERS. The other eight
# listings are left with none on purpose, so the "New" rating badge and "No
# reviews yet" empty state both get exercised honestly.
STARTER_REVIEWS = [
    dict(
        listing_title="Family house with backyard",
        renter_key="dilnoza",
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
        listing_title="Family house with backyard",
        renter_key="marcus",
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
        listing_title="Family house with backyard",
        renter_key="aliya",
        rating=4,
        comment=(
            "Really nice house overall - spacious kitchen and a lovely yard. Parking "
            "was a little tight with two cars, but otherwise a great stay."
        ),
        start_date=date(2026, 4, 18),
        end_date=date(2026, 4, 21),
        guest_count=3,
    ),
    dict(
        listing_title="2021 Toyota Camry",
        renter_key="javlon",
        rating=5,
        comment=(
            "Clean, reliable car for our trip down to Portland. Elyor made pickup and "
            "drop-off easy and was flexible when our flight got delayed."
        ),
        start_date=date(2026, 3, 12),
        end_date=date(2026, 3, 16),
        guest_count=2,
    ),
    dict(
        listing_title="2021 Toyota Camry",
        renter_key="sarah",
        rating=4,
        comment="Good value for a week-long rental. Car ran great, just wish the tank was fuller at pickup.",
        start_date=date(2026, 2, 2),
        end_date=date(2026, 2, 9),
        guest_count=1,
    ),
    dict(
        listing_title="Sunlit loft near Prospect Park",
        renter_key="farrukh",
        rating=5,
        comment=(
            "Beautiful loft, five minutes from the park and close to a couple of great "
            "Uzbek restaurants. Dilshod was a wonderful host and even left fresh non "
            "bread waiting for us."
        ),
        start_date=date(2026, 7, 3),
        end_date=date(2026, 7, 6),
        guest_count=2,
    ),
    dict(
        listing_title="Sunlit loft near Prospect Park",
        renter_key="aliya",
        rating=5,
        comment="Stayed here for a long weekend and loved every minute. Bright, clean, and exactly like the photos.",
        start_date=date(2026, 6, 20),
        end_date=date(2026, 6, 23),
        guest_count=1,
    ),
    dict(
        listing_title="Cozy 2BR near the park",
        renter_key="sarah",
        rating=4,
        comment="Great location and a quiet block. Would happily book again next time we're visiting family in Philly.",
        start_date=date(2026, 5, 22),
        end_date=date(2026, 5, 25),
        guest_count=3,
    ),
]


_demo_user_password_cache: str | None = None


def _resolve_demo_user_password() -> str:
    """One shared login for every seeded starter host/renter account.

    Comes from DEMO_USER_PASSWORD in the environment; if unset, a random one
    is generated and printed once, then cached for the rest of this process
    so seed_starter_listings and seed_starter_reviews (both of which call
    this) can't end up handing out two different random passwords in the
    same run.
    """
    global _demo_user_password_cache
    if _demo_user_password_cache is None:
        password = settings.demo_user_password
        if not password:
            password = secrets.token_urlsafe(12)
            print(f"[seed] No DEMO_USER_PASSWORD set — generated one for the starter accounts: {password}")
        _demo_user_password_cache = password
    return _demo_user_password_cache


def _seed_user(
    db: Session,
    *,
    email: str,
    full_name: str,
    role: models.UserRole,
    verified: bool,
    password: str,
) -> models.User:
    """Create the user if it's missing, else just keep name/verified in sync.

    Never touches password_hash on an existing row, so re-seeding can't lock
    anyone out of an account that's already in use.
    """
    user = db.query(models.User).filter(models.User.email == email).first()
    if user is None:
        user = models.User(
            full_name=full_name,
            email=email,
            role=role,
            verified=verified,
            password_hash=hash_password(password),
        )
        db.add(user)
        db.flush()
    else:
        user.full_name = full_name
        user.verified = verified
    return user


def _cleanup_old_starter_data(db: Session) -> None:
    """One-time cleanup of the single-host, single-listing seed set this replaced.

    Only ever touches rows owned by the old demo identities below, so it's
    safe alongside real data. Can be deleted once nobody has the old data
    lying around anymore.
    """
    old_host_email = "starter-host@uzbekrentals.app"
    old_reviewer_prefix = "demo-review-"

    old_host = db.query(models.User).filter(models.User.email == old_host_email).first()
    if old_host is not None:
        old_listing_ids = [
            row.id for row in db.query(models.Listing.id).filter(models.Listing.host_id == old_host.id).all()
        ]
        if old_listing_ids:
            db.query(models.Review).filter(models.Review.listing_id.in_(old_listing_ids)).delete(
                synchronize_session=False
            )
            db.query(models.Booking).filter(models.Booking.listing_id.in_(old_listing_ids)).delete(
                synchronize_session=False
            )
            db.query(models.Listing).filter(models.Listing.id.in_(old_listing_ids)).delete(
                synchronize_session=False
            )
        db.query(models.User).filter(models.User.id == old_host.id).delete(synchronize_session=False)

    old_reviewer_ids = [
        row.id for row in db.query(models.User).filter(models.User.email.like(f"{old_reviewer_prefix}%")).all()
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

    db.commit()


def seed_starter_listings(db: Session) -> None:
    """Keep SEED_HOSTS and their STARTER_LISTINGS in sync.

    Re-runs on every startup. Only ever touches the seeded host accounts
    (email prefix host-) and listings owned by them, so it's safe to edit
    either list and see the change reflected without hand-editing the
    database, and it never touches a real host's account or listings.
    """
    _cleanup_old_starter_data(db)

    password = _resolve_demo_user_password()
    hosts = {
        data["key"]: _seed_user(
            db,
            email=data["email"],
            full_name=data["full_name"],
            role=models.UserRole.host,
            verified=data["verified"],
            password=password,
        )
        for data in SEED_HOSTS
    }

    host_ids = [host.id for host in hosts.values()]
    db.query(models.Listing).filter(models.Listing.host_id.in_(host_ids)).delete(synchronize_session=False)

    for data in STARTER_LISTINGS:
        host_key = data["host_key"]
        listing_fields = {k: v for k, v in data.items() if k != "host_key"}
        listing_fields.setdefault("verified", False)
        listing_fields.setdefault("guest_favorite", False)
        db.add(models.Listing(host_id=hosts[host_key].id, status=models.ListingStatus.active, **listing_fields))

    db.commit()


def seed_starter_reviews(db: Session) -> None:
    """Keep SEED_RENTERS and STARTER_REVIEWS in sync.

    Re-runs on every startup. Only ever touches the seeded renter accounts
    (email prefix renter-) and the bookings/reviews they created against the
    starter listings, so it's safe to run repeatedly and never touches real
    users. Must run after seed_starter_listings, since starter listing ids
    are regenerated on every reseed and this looks them up by title.
    """
    password = _resolve_demo_user_password()
    renters = {
        data["key"]: _seed_user(
            db,
            email=data["email"],
            full_name=data["full_name"],
            role=models.UserRole.renter,
            verified=False,
            password=password,
        )
        for data in SEED_RENTERS
    }
    renter_ids = [renter.id for renter in renters.values()]

    listing_titles = {row["listing_title"] for row in STARTER_REVIEWS}
    listings_by_title = {
        listing.title: listing
        for listing in db.query(models.Listing).filter(models.Listing.title.in_(listing_titles)).all()
    }

    starter_listing_ids = [listing.id for listing in listings_by_title.values()]
    if starter_listing_ids:
        old_booking_ids = [
            row.id
            for row in db.query(models.Booking)
            .filter(
                models.Booking.renter_id.in_(renter_ids),
                models.Booking.listing_id.in_(starter_listing_ids),
            )
            .all()
        ]
        if old_booking_ids:
            db.query(models.Review).filter(models.Review.booking_id.in_(old_booking_ids)).delete(
                synchronize_session=False
            )
            db.query(models.Booking).filter(models.Booking.id.in_(old_booking_ids)).delete(
                synchronize_session=False
            )
    db.flush()

    for data in STARTER_REVIEWS:
        listing = listings_by_title.get(data["listing_title"])
        if listing is None:
            continue
        renter = renters[data["renter_key"]]

        nights = (data["end_date"] - data["start_date"]).days
        booking = models.Booking(
            listing_id=listing.id,
            renter_id=renter.id,
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
                author_id=renter.id,
                rating=data["rating"],
                comment=data["comment"],
            )
        )

    db.commit()


def seed_demo_admin(db: Session) -> None:
    """Make sure the demo admin account exists so /admin is reachable.

    Re-runs on every startup; only ever touches this one row.
    """
    admin = db.query(models.User).filter(models.User.email == DEMO_ADMIN_EMAIL).first()
    if admin is None:
        password = settings.demo_admin_password
        if not password:
            password = secrets.token_urlsafe(12)
            print(
                f"[seed] No DEMO_ADMIN_PASSWORD set — generated one for "
                f"{DEMO_ADMIN_EMAIL}: {password}"
            )
        db.add(
            models.User(
                full_name="Site Admin",
                email=DEMO_ADMIN_EMAIL,
                password_hash=hash_password(password),
                role=models.UserRole.admin,
            )
        )
        db.commit()
