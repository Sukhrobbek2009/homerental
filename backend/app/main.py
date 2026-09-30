import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import settings
from .database import SessionLocal
from .ratelimit import client_ip
from .routers import admin, auth, bookings, listings, messages, pages, reviews, saved
from .seed import seed_demo_admin, seed_starter_listings, seed_starter_reviews

# Uvicorn only configures its own loggers; this gives the app's a handler too.
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
request_logger = logging.getLogger("app.requests")
error_logger = logging.getLogger("app.errors")

GENERIC_ERROR_MESSAGE = "Something went wrong on our side. Please try again."


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



# Registered before CORSMiddleware so it runs inside it: the generic 500 below
# still gets CORS headers, and the browser shows it instead of a CORS error.
@app.middleware("http")
async def log_requests_and_hide_errors(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # The traceback stays in the server log; the client only gets an id
        # to quote, which matches the log line.
        error_id = uuid.uuid4().hex[:12]
        error_logger.exception("Unhandled error %s on %s %s", error_id, request.method, request.url.path)
        response = JSONResponse(status_code=500, content={"detail": GENERIC_ERROR_MESSAGE, "error_id": error_id})
    elapsed_ms = (time.perf_counter() - started) * 1000
    request_logger.info(
        "%s %s %s %.1fms ip=%s", request.method, request.url.path, response.status_code, elapsed_ms, client_ip(request)
    )
    return response


# Only the listed origins; the frontend sends its token in the Authorization
# header, never cookies, so credentials aren't needed.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
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
