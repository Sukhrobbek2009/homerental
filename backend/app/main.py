from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import SessionLocal
from .routers import admin, auth, bookings, listings, messages, pages, reviews, saved
from .seed import seed_demo_admin, seed_starter_listings, seed_starter_reviews


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.seed_demo_data:
        db = SessionLocal()
        try:
            seed_starter_listings(db)
            seed_starter_reviews(db)
            seed_demo_admin(db)
        finally:
            db.close()
    yield


app = FastAPI(title="Uzbek Rentals API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(listings.router)
app.include_router(bookings.router)
app.include_router(reviews.router)
app.include_router(saved.router)
app.include_router(messages.router)
app.include_router(admin.router)
app.include_router(pages.router)


@app.get("/api/health")
@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
def public_config() -> dict[str, str]:
    return {"google_client_id": settings.google_client_id}
