
import os
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import httpx
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import (
    create_engine, String, DateTime, Text, select, or_
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, sessionmaker, Session
)

# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

DATABASE_URL = os.getenv(
    "DATABASE_URL", "sqlite:///./findme.db"
)
FRONTEND_ORIGIN = os.getenv(
    "FRONTEND_ORIGIN", "http://localhost:5173"
)
NIPOST_MOCK_MODE = (
    os.getenv("NIPOST_MOCK_MODE", "true").lower() == "true"
)
NIPOST_API_BASE_URL = os.getenv(
    "NIPOST_API_BASE_URL", ""
).rstrip("/")
NIPOST_API_KEY = os.getenv("NIPOST_API_KEY", "")
NIPOST_LOOKUP_PATH = os.getenv("NIPOST_LOOKUP_PATH", "")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
    if DATABASE_URL.startswith("sqlite")
    else {},
)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


# --------------------------------------------------
# POSTCODE NORMALIZATION AND VALIDATION
# --------------------------------------------------

def normalize_postcode(value: str) -> str:
    """
    Remove spaces and hyphens from a postcode.
    Example: OG 10 A16 BN 15 -> OG10A16BN15
    """
    return re.sub(r"[\s-]+", "", value).upper()


def postcode_format_is_valid(value: str) -> bool:
    """
    Check for exactly 11 alphanumeric characters
    after removing spaces and hyphens.

    This checks format only, not official existence.
    """
    normalized = normalize_postcode(value)
    return bool(re.fullmatch(r"[A-Z0-9]{11}", normalized))


def validate_postcode_input(value: str) -> str:
    """
    Reusable Pydantic validator.
    Keeps the normalized postcode in the request model.
    """
    normalized = normalize_postcode(value)

    if not postcode_format_is_valid(normalized):
        raise ValueError(
            "Enter a postcode containing exactly 11 "
            "letters or digits. Spaces and hyphens are allowed."
        )

    return normalized


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

class Base(DeclarativeBase):
    pass


class DeliveryStatus(str, Enum):
    pending = "pending"
    dispatched = "dispatched"
    delivered = "delivered"
    cancelled = "cancelled"


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    customer_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20))
    postcode: Mapped[str] = mapped_column(String(11))
    state: Mapped[str] = mapped_column(String(80))
    lga: Mapped[str] = mapped_column(String(100))
    town: Mapped[str] = mapped_column(String(100))
    street: Mapped[str] = mapped_column(String(180))
    building_number: Mapped[str] = mapped_column(String(30))
    landmark: Mapped[str] = mapped_column(String(200))
    instructions: Mapped[str] = mapped_column(Text, default="")
    order_reference: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )
    postcode_verified: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------
# API SCHEMAS
# --------------------------------------------------

class PostcodeRequest(BaseModel):
    # Allow spaces and hyphens in formatted input.
    postcode: str = Field(min_length=1, max_length=20)

    @field_validator("postcode")
    @classmethod
    def check_postcode(cls, value: str) -> str:
        return validate_postcode_input(value)


class DeliveryCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=20)
    postcode: str = Field(min_length=1, max_length=20)
    state: str = Field(min_length=2, max_length=80)
    lga: str = Field(min_length=2, max_length=100)
    town: str = Field(min_length=2, max_length=100)
    street: str = Field(min_length=2, max_length=180)
    building_number: str = Field(min_length=1, max_length=30)
    landmark: str = Field(min_length=2, max_length=200)
    instructions: str = Field(default="", max_length=1000)
    order_reference: str = Field(min_length=1, max_length=80)
    postcode_verified: bool = False

    @field_validator("postcode")
    @classmethod
    def check_postcode(cls, value: str) -> str:
        return validate_postcode_input(value)


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_name: str
    phone: str
    postcode: str
    state: str
    lga: str
    town: str
    street: str
    building_number: str
    landmark: str
    instructions: str
    order_reference: str
    status: str
    postcode_verified: bool
    created_at: datetime


class StatusUpdate(BaseModel):
    status: DeliveryStatus


# --------------------------------------------------
# FASTAPI APPLICATION
# --------------------------------------------------

app = FastAPI(
    title="FindMe NG API",
    description="Smart address and delivery assistant",
    version="0.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/health")
def health():
    return {"status": "ok", "service": "FindMe NG"}


# --------------------------------------------------
# POSTCODE VALIDATION
# --------------------------------------------------

@app.post("/api/postcodes/validate")
async def validate_postcode_endpoint(
    payload: PostcodeRequest,
):
    # Pydantic has already normalized and checked the format.
    postcode = payload.postcode

    if NIPOST_MOCK_MODE:
        return {
            "postcode": postcode,
            "valid": False,
            "verified": False,
            "mode": "mock",
            "message": (
                "Postcode format accepted. "
                "Official NIPOST verification has not been performed."
            ),
            "location": None,
        }

    if not all([
        NIPOST_API_BASE_URL,
        NIPOST_API_KEY,
        NIPOST_LOOKUP_PATH,
    ]):
        raise HTTPException(
            status_code=503,
            detail="Official postcode API is not configured.",
        )

    url = (
        f"{NIPOST_API_BASE_URL}/"
        f"{NIPOST_LOOKUP_PATH.lstrip('/')}"
    )

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                url,
                params={"postcode": postcode},
                headers={
                    "Authorization": f"Bearer {NIPOST_API_KEY}",
                    "Accept": "application/json",
                },
            )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="NIPOST request timed out.",
        )
    except httpx.RequestError:
        raise HTTPException(
            status_code=502,
            detail="Could not reach NIPOST.",
        )

    if response.status_code in (401, 403):
        raise HTTPException(
            status_code=502,
            detail="NIPOST rejected the credentials or permissions.",
        )

    if response.status_code == 404:
        return {
            "postcode": postcode,
            "valid": False,
            "verified": True,
            "mode": "official",
            "message": "The official service did not find this postcode.",
            "location": None,
        }

    if response.status_code == 429:
        raise HTTPException(
            status_code=503,
            detail="NIPOST rate limit reached. Try again later.",
        )

    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"NIPOST returned HTTP {response.status_code}.",
        )

    try:
        data = response.json()
    except ValueError:
        raise HTTPException(
            status_code=502,
            detail="NIPOST returned an unexpected response.",
        )

    # Map this response to verified/valid/location after
    # confirming the actual response schema in NIPOST docs.
    return {
        "postcode": postcode,
        "valid": None,
        "verified": False,
        "mode": "official_unmapped",
        "message": (
            "Response received. Official response mapping is required."
        ),
        "raw_response": data,
    }


# --------------------------------------------------
# DELIVERY RECORDS
# --------------------------------------------------

@app.post(
    "/api/deliveries",
    response_model=DeliveryOut,
    status_code=201,
)
def create_delivery(
    payload: DeliveryCreate,
    db: Session = Depends(get_db),
):
    record_data = payload.model_dump(exclude={"postcode"})

    record = Delivery(
        **record_data,
        postcode=payload.postcode,
        status=DeliveryStatus.pending.value,
    )

    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.get("/api/deliveries", response_model=list[DeliveryOut])
def list_deliveries(
    search: Optional[str] = Query(default=None, max_length=120),
    status: Optional[DeliveryStatus] = None,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    stmt = select(Delivery)

    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Delivery.customer_name.ilike(term),
                Delivery.phone.ilike(term),
                Delivery.postcode.ilike(term),
                Delivery.order_reference.ilike(term),
                Delivery.landmark.ilike(term),
            )
        )

    if status:
        stmt = stmt.where(Delivery.status == status.value)

    stmt = stmt.order_by(Delivery.created_at.desc())

    return list(
        db.scalars(stmt.offset(offset).limit(limit)).all()
    )


@app.patch(
    "/api/deliveries/{delivery_id}/status",
    response_model=DeliveryOut,
)
def update_delivery_status(
    delivery_id: str,
    payload: StatusUpdate,
    db: Session = Depends(get_db),
):
    record = db.get(Delivery, delivery_id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Delivery record not found.",
        )

    record.status = payload.status.value
    db.commit()
    db.refresh(record)
    return record
