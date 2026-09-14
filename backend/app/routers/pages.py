import re
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["pages"])

# backend/app/routers/pages.py -> repo root (three levels up)
FRONTEND_DIR = Path(__file__).resolve().parents[3]

PAGE_FILES = {
    "index": "index.html",
    "listings": "listings.html",
    "listing-detail": "listing-detail.html",
    "car-listing-detail": "car-listing-detail.html",
    "auth": "auth.html",
    "host-dashboard": "host-dashboard.html",
    "renter-dashboard": "renter-dashboard.html",
    "messages": "messages.html",
    "profile": "profile.html",
}

# Strips a leading Jekyll front matter block (--- ... ---) used only to give
# these pages clean permalinks when GitHub Pages builds the site with Jekyll.
_FRONT_MATTER_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)


def _page(key: str) -> HTMLResponse:
    path = FRONTEND_DIR / PAGE_FILES[key]
    if not path.exists():
        raise HTTPException(status_code=500, detail=f"Missing frontend file: {PAGE_FILES[key]}")
    html = _FRONT_MATTER_RE.sub("", path.read_text(encoding="utf-8"), count=1)
    return HTMLResponse(html)


@router.get("/", include_in_schema=False)
def home() -> HTMLResponse:
    return _page("index")


@router.get("/listings", include_in_schema=False)
def listings_page() -> HTMLResponse:
    return _page("listings")


@router.get("/listings/property", include_in_schema=False)
def listing_detail_page() -> HTMLResponse:
    return _page("listing-detail")


@router.get("/listings/car", include_in_schema=False)
def car_listing_detail_page() -> HTMLResponse:
    return _page("car-listing-detail")


@router.get("/login", include_in_schema=False)
@router.get("/signup", include_in_schema=False)
def auth_page() -> HTMLResponse:
    return _page("auth")


@router.get("/host-dashboard", include_in_schema=False)
def host_dashboard_page() -> HTMLResponse:
    return _page("host-dashboard")


@router.get("/renter-dashboard", include_in_schema=False)
def renter_dashboard_page() -> HTMLResponse:
    return _page("renter-dashboard")


@router.get("/messages", include_in_schema=False)
def messages_page() -> HTMLResponse:
    return _page("messages")


@router.get("/profile", include_in_schema=False)
def profile_page() -> HTMLResponse:
    return _page("profile")
