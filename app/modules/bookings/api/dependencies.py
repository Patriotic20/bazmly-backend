"""Booking dependencies, plus the seam that queues the confirmation notification.

The notification is queued rather than written inline. A booking that the database
has already accepted must not be rolled back because delivery failed, and the
customer is waiting on the response — so this runs after the response is on the
wire.

This used to send an SMS through Eskiz. With the SMS layer gone the same seam now
writes the in-app notification and fires the push, so a confirmed booking still
tells the customer something.
"""

import logging
from typing import Annotated

from fastapi import BackgroundTasks, Depends

from app.core.dependencies import SessionDep
from app.modules.bookings.schemas import BookingOwnerDetail
from app.modules.bookings.services import AvailabilityService, BookingService

logger = logging.getLogger("app.bookings")


def get_booking_service(session: SessionDep) -> BookingService:
    return BookingService(session)


def get_availability_service(session: SessionDep) -> AvailabilityService:
    return AvailabilityService(session)


BookingServiceDep = Annotated[BookingService, Depends(get_booking_service)]
AvailabilityServiceDep = Annotated[AvailabilityService, Depends(get_availability_service)]


def queue_booking_confirmation(background: BackgroundTasks, detail: BookingOwnerDetail) -> None:
    """Schedule the confirmation notification for after the response."""
    background.add_task(
        _send_booking_confirmation,
        user_id=detail.booking.user_id,
        venue=detail.venue_name,
        date=detail.booking.booking_date.strftime("%d.%m"),
        time=detail.booking.start_time.strftime("%H:%M"),
    )


async def _send_booking_confirmation(*, user_id: int, venue: str, date: str, time: str) -> None:
    """Runs after the response, on its own session.

    The request's session is closed by the time a background task runs, so this opens
    a new one. Failures are logged and swallowed: the booking is already committed and
    there is nothing left to abort.

    TODO(queue): `BackgroundTasks` runs in the web worker, so a restart loses anything
    in flight. Replace with `arq` or Celery before production — recorded in
    DECISIONS.md.
    """
    from app.core.database.db_helper import db_helper
    from app.modules.engagement.services import NotificationService

    title = "Bron tasdiqlandi"
    body = f"{venue} — {date}, {time}"
    try:
        async with db_helper.session_factory() as session:
            service = NotificationService(session)
            await service.notify_in_transaction(
                user_id=user_id,
                notification_type="booking_confirmed",
                title=title,
                body=body,
            )
            await session.commit()
            await service.push_after_commit(user_id, title, body)
    except Exception:
        logger.warning("booking confirmation failed for user_id=%s", user_id, exc_info=True)
