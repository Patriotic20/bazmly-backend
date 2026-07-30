"""Provider callbacks: signed, idempotent, and answered in the provider's dialect."""

import hashlib
import hmac
import json
from datetime import time
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.payments.enums import PaymentKind, PaymentStatus
from app.modules.payments.models import Payment
from tests.repositories import factories

PAYME_SECRET = "payme-test-secret"
CLICK_SECRET = "click-test-secret"
TRANSACTION_ID = "tx-12345"


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def seed_payment(session: AsyncSession, provider: str) -> Payment:
    """A created-but-unsettled payment, which is what a callback settles."""
    group = await factories.make_venue_group(session)
    venue = await factories.make_venue(session, group=group)
    await factories.make_working_hours(session, venue, time(8, 0), time(23, 0))
    user = await factories.make_user(session)

    from datetime import timedelta

    from app.core.database.mixins import utcnow_naive
    from app.modules.bookings.models import Booking
    from app.modules.bookings.schemas import TableReservationCreate
    from app.modules.bookings.services import BookingService

    table = await factories.make_table(session, venue, seats=4)
    detail = await BookingService(session).create_table_reservation(
        user.id,
        TableReservationCreate(
            venue_id=venue.id,
            table_id=table.id,
            booking_date=utcnow_naive().date() + timedelta(days=7),
            start_time=time(18, 0),
            end_time=time(20, 0),
            guests_count=2,
            contact_name="Guest",
            contact_phone="+998901112233",
        ),
        1,
    )
    assert isinstance(detail.booking.id, int)

    payment = Payment(
        user_id=user.id,
        booking_id=detail.booking.id,
        provider=provider,
        provider_transaction_id=TRANSACTION_ID,
        kind=PaymentKind.DEPOSIT,
        amount=Decimal("100000.00"),
        currency="UZS",
        status=PaymentStatus.CREATED,
    )
    session.add(payment)
    await session.flush()
    _ = Booking  # imported for the type it documents
    return payment


async def test_payme_rejects_an_invalid_signature(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wrong signature never reaches the database, and the refusal is JSON-RPC.

    Answering with our own error body would leave Payme retrying forever against a
    shape it cannot parse.
    """
    monkeypatch.setattr(settings.webhooks, "payme_secret", PAYME_SECRET)
    body = json.dumps({"params": {"id": TRANSACTION_ID, "state": 2}}).encode()

    response = await api_client.post(
        "/api/v1/webhooks/payme",
        content=body,
        headers={"X-Signature": "deadbeef", "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -32504


async def test_payme_missing_signature_is_rejected(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.webhooks, "payme_secret", PAYME_SECRET)
    body = json.dumps({"params": {"id": TRANSACTION_ID}}).encode()

    response = await api_client.post(
        "/api/v1/webhooks/payme",
        content=body,
        headers={"Content-Type": "application/json"},
    )

    assert response.json()["error"]["code"] == -32504


async def test_unconfigured_provider_rejects_everything(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty secret means the provider is off, not open.

    Without this, an empty configured secret compared against an empty header
    would authenticate every caller.
    """
    monkeypatch.setattr(settings.webhooks, "click_secret", "")
    body = json.dumps({"click_trans_id": TRANSACTION_ID, "error": 0}).encode()

    response = await api_client.post(
        "/api/v1/webhooks/click",
        content=body,
        headers={"X-Signature": sign(body, "anything"), "Content-Type": "application/json"},
    )

    assert response.json()["error"] == -1


async def test_the_same_transaction_twice_produces_one_payment(
    api_client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Providers retry. Settling by `(provider, provider_transaction_id)` means a
    replay is a no-op rather than a second settlement."""
    monkeypatch.setattr(settings.webhooks, "click_secret", CLICK_SECRET)
    payment = await seed_payment(session, "click")

    body = json.dumps({"click_trans_id": TRANSACTION_ID, "error": 0}).encode()
    headers = {"X-Signature": sign(body, CLICK_SECRET), "Content-Type": "application/json"}

    first = await api_client.post("/api/v1/webhooks/click", content=body, headers=headers)
    second = await api_client.post("/api/v1/webhooks/click", content=body, headers=headers)

    assert first.json() == {"error": 0, "error_note": "Success"}
    assert second.json() == {"error": 0, "error_note": "Success"}

    rows = await session.execute(
        select(func.count())
        .select_from(Payment)
        .where(Payment.provider_transaction_id == TRANSACTION_ID)
    )
    assert rows.scalar_one() == 1

    settled = await session.get(Payment, payment.id)
    assert settled is not None
    assert settled.status == PaymentStatus.PAID


async def test_unknown_transaction_gets_the_providers_not_found_code(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings.webhooks, "click_secret", CLICK_SECRET)
    body = json.dumps({"click_trans_id": "no-such-tx", "error": 0}).encode()

    response = await api_client.post(
        "/api/v1/webhooks/click",
        content=body,
        headers={"X-Signature": sign(body, CLICK_SECRET), "Content-Type": "application/json"},
    )

    assert response.json()["error"] == -5


async def test_webhooks_take_no_jwt(
    api_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No Authorization header anywhere in the flow — the caller is a server,
    authenticated by an HMAC over the raw body."""
    monkeypatch.setattr(settings.webhooks, "payme_secret", PAYME_SECRET)
    body = json.dumps({"params": {"id": "nope", "state": 2}}).encode()

    response = await api_client.post(
        "/api/v1/webhooks/payme",
        content=body,
        headers={"X-Signature": sign(body, PAYME_SECRET), "Content-Type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["error"]["code"] == -31003
