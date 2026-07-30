from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.orders.models import (
    Order,
    OrderItem,
    OrderItemStatus,
    OrderPayment,
    OrderStatus,
)
from app.modules.orders.models.order_status_history import OrderStatusHistory
from app.modules.venues.models import Venue, VenueTable

# A table is occupied while its order is in any state but these two.
CLOSED_ORDER_STATUSES = (OrderStatus.COMPLETED, OrderStatus.CANCELLED)

# The kitchen queue is a per-dish question, not a per-check one.
KITCHEN_ITEM_STATUSES = (OrderItemStatus.SENT_TO_KITCHEN, OrderItemStatus.COOKING)

# Closing is only legal from a state where the food has actually been delivered.
CLOSEABLE_ORDER_STATUSES = (OrderStatus.SERVED, OrderStatus.AWAITING_PAYMENT)


@dataclass(frozen=True, slots=True)
class TableBoardRow:
    """One tile on the Stollar board.

    `order` is `None` for a free table — that is the whole point of the left join,
    and why there is no `venue_tables.state` column that could disagree with it.
    """

    table: VenueTable
    order: Order | None


@dataclass(frozen=True, slots=True)
class KitchenQueueRow:
    item: OrderItem
    table_number: int | None


class OrderRepository:
    """An open check on a table right now. Not a booking.

    `open_for_table` deliberately does not pre-check for an existing open order:
    the `one_open_order_per_table` partial unique index is the authority, so two
    waiters tapping the same empty table produce one check and one
    `IntegrityError` rather than two checks.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, order_id: int) -> Order | None:
        result = await self.session.execute(select(Order).where(Order.id == order_id))
        return result.scalar_one_or_none()

    async def table_board(
        self, venue_id: int, zone_id: int | None = None
    ) -> Sequence[TableBoardRow]:
        """Every active table with its live order, or `None`.

        The partial unique index guarantees at most one live order per table, so
        this left join can never fan out.
        """
        stmt = (
            select(VenueTable, Order)
            .outerjoin(
                Order,
                (Order.table_id == VenueTable.id) & (Order.status.notin_(CLOSED_ORDER_STATUSES)),
            )
            .where(VenueTable.venue_id == venue_id, VenueTable.is_active.is_(True))
        )
        if zone_id is not None:
            stmt = stmt.where(VenueTable.zone_id == zone_id)

        result = await self.session.execute(stmt.order_by(VenueTable.number))
        return [TableBoardRow(table=row[0], order=row[1]) for row in result.all()]

    async def next_order_number(self, venue_id: int, business_date: date_type) -> int:
        """Per-branch, per-day sequence.

        The venue row is locked `FOR UPDATE` first, which serialises numbering
        within a branch for the rest of the transaction. A bare `MAX + 1` would let
        two waiters read the same maximum and collide on
        `UNIQUE (venue_id, business_date, order_number)`.
        """
        await self.session.execute(select(Venue.id).where(Venue.id == venue_id).with_for_update())
        result = await self.session.execute(
            select(func.coalesce(func.max(Order.order_number), 0) + 1).where(
                Order.venue_id == venue_id, Order.business_date == business_date
            )
        )
        return int(result.scalar_one())

    async def open_for_table(
        self,
        venue_id: int,
        table_id: int,
        staff_id: int,
        business_date: date_type,
        now: datetime,
        guests_count: int | None = None,
        currency: str = "UZS",
    ) -> Order:
        """Opens a check. Lets `one_open_order_per_table` raise on a double open."""
        order = Order(
            venue_id=venue_id,
            table_id=table_id,
            order_number=await self.next_order_number(venue_id, business_date),
            business_date=business_date,
            status=OrderStatus.OPEN,
            guests_count=guests_count,
            opened_by_staff_id=staff_id,
            waiter_staff_id=staff_id,
            currency=currency,
            opened_at=now,
        )
        self.session.add(order)
        await self.session.flush()
        return order

    async def get_active_for_table(self, table_id: int) -> Order | None:
        result = await self.session.execute(
            select(Order).where(
                Order.table_id == table_id, Order.status.notin_(CLOSED_ORDER_STATUSES)
            )
        )
        return result.scalar_one_or_none()

    async def list_for_board(
        self,
        venue_id: int,
        statuses: Sequence[str] | None,
        business_date: date_type,
    ) -> Sequence[Order]:
        """The Buyurtmalar list. Uses the `(venue_id, status, opened_at)` index."""
        stmt = select(Order).where(Order.venue_id == venue_id, Order.business_date == business_date)
        if statuses:
            stmt = stmt.where(Order.status.in_(statuses))
        result = await self.session.execute(stmt.order_by(Order.opened_at.desc()))
        return result.scalars().all()

    async def add_items(self, order_id: int, items: Sequence[OrderItem]) -> Sequence[OrderItem]:
        """Appends to an open check.

        Callers must have snapshotted `unit_price` and `name_snapshot` already —
        resolving them here would join to live `menu_items` and silently reprice
        an old check when the menu changes.
        """
        for item in items:
            item.order_id = order_id
            self.session.add(item)
        await self.session.flush()
        return items

    async def list_items(self, order_id: int) -> Sequence[OrderItem]:
        result = await self.session.execute(
            select(OrderItem)
            .where(OrderItem.order_id == order_id)
            .order_by(OrderItem.added_at, OrderItem.id)
        )
        return result.scalars().all()

    async def recalculate_totals(self, order_id: int) -> Order | None:
        """One `UPDATE ... FROM (SELECT SUM ...)`, so the totals can never drift
        from the items in the window between two statements."""
        totals = (
            select(
                func.coalesce(func.sum(OrderItem.total_price), 0).label("subtotal"),
                func.coalesce(func.sum(OrderItem.discount_amount), 0).label("discount"),
            )
            .where(
                OrderItem.order_id == order_id,
                OrderItem.status != OrderItemStatus.CANCELLED,
            )
            .subquery()
        )
        result = await self.session.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(
                subtotal=select(totals.c.subtotal).scalar_subquery(),
                discount_amount=select(totals.c.discount).scalar_subquery(),
                total_amount=(
                    select(totals.c.subtotal - totals.c.discount).scalar_subquery()
                    + Order.service_charge
                ),
            )
            .returning(Order)
        )
        await self.session.flush()
        return result.scalars().one_or_none()

    async def close(self, order_id: int, staff_id: int, now: datetime) -> Order | None:
        """Guarded transition. Returns `None` if the check was not ready to close,
        so closing twice is a no-op rather than a second receipt."""
        result = await self.session.execute(
            update(Order)
            .where(Order.id == order_id, Order.status.in_(CLOSEABLE_ORDER_STATUSES))
            .values(status=OrderStatus.COMPLETED, closed_at=now, closed_by_staff_id=staff_id)
            .returning(Order)
        )
        order = result.scalars().one_or_none()
        if order is None:
            return None
        self.session.add(
            OrderStatusHistory(
                order_id=order_id,
                to_status=OrderStatus.COMPLETED,
                changed_by_staff_id=staff_id,
                changed_at=now,
            )
        )
        await self.session.flush()
        return order

    async def cancel(
        self, order_id: int, staff_id: int, now: datetime, reason: str | None = None
    ) -> Order | None:
        result = await self.session.execute(
            update(Order)
            .where(Order.id == order_id, Order.status.notin_(CLOSED_ORDER_STATUSES))
            .values(
                status=OrderStatus.CANCELLED,
                cancelled_at=now,
                cancel_reason=reason,
                closed_by_staff_id=staff_id,
            )
            .returning(Order)
        )
        order = result.scalars().one_or_none()
        if order is None:
            return None
        self.session.add(
            OrderStatusHistory(
                order_id=order_id,
                to_status=OrderStatus.CANCELLED,
                changed_by_staff_id=staff_id,
                comment=reason,
                changed_at=now,
            )
        )
        await self.session.flush()
        return order

    async def kitchen_queue(self, venue_id: int) -> Sequence[KitchenQueueRow]:
        """Oshpaz's dish queue, oldest first, with the table number to call out."""
        result = await self.session.execute(
            select(OrderItem, VenueTable.number)
            .join(Order, Order.id == OrderItem.order_id)
            .outerjoin(VenueTable, VenueTable.id == Order.table_id)
            .where(
                Order.venue_id == venue_id,
                OrderItem.status.in_(KITCHEN_ITEM_STATUSES),
            )
            .order_by(OrderItem.added_at, OrderItem.id)
        )
        return [KitchenQueueRow(item=row[0], table_number=row[1]) for row in result.all()]

    async def add_payment(self, payment: OrderPayment) -> OrderPayment:
        """Split payments are one order, several rows. Whether the total covers the
        check is the service's call before closing, not a constraint."""
        self.session.add(payment)
        await self.session.flush()
        return payment

    async def list_payments(self, order_id: int) -> Sequence[OrderPayment]:
        result = await self.session.execute(
            select(OrderPayment)
            .where(OrderPayment.order_id == order_id)
            .order_by(OrderPayment.paid_at, OrderPayment.id)
        )
        return result.scalars().all()

    async def sum_payments(self, order_id: int) -> Decimal:
        result = await self.session.execute(
            select(func.coalesce(func.sum(OrderPayment.amount), 0)).where(
                OrderPayment.order_id == order_id
            )
        )
        return Decimal(result.scalar_one())

    async def set_status(self, order_id: int, status: str) -> Order | None:
        """Advance a live check. Refuses to touch a completed or cancelled one, so
        a late call cannot reopen a closed order."""
        result = await self.session.execute(
            update(Order)
            .where(Order.id == order_id, Order.status.notin_(CLOSED_ORDER_STATUSES))
            .values(status=status)
            .returning(Order)
        )
        await self.session.flush()
        return result.scalars().one_or_none()
