from collections.abc import Sequence
from datetime import date as date_type
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import (
    NotFoundError,
    PaymentIncompleteError,
    ValidationFailedError,
)
from app.core.integrity import translate_integrity_error
from app.modules.menu.repositories import MenuItemRepository
from app.modules.orders.enums import OrderItemStatus, OrderKind, OrderStatus
from app.modules.orders.models import Order, OrderItem, OrderPayment
from app.modules.orders.repositories import OrderRepository
from app.modules.orders.schemas import (
    KitchenQueueItem,
    OrderCancel,
    OrderDetailRead,
    OrderItemCreate,
    OrderItemRead,
    OrderListItem,
    OrderOpen,
    OrderPaymentCreate,
    OrderPaymentRead,
    OrderRead,
    ReceiptRead,
    TableBoardRow,
)
from app.modules.orders.services.receipt_service import ReceiptService
from app.modules.staff.services import StaffService
from app.modules.venues.repositories import VenueTableRepository

MONEY = Decimal("0.01")

PERM_OPEN = "orders.open"
PERM_ADD_ITEMS = "orders.add_items"
PERM_CLOSE = "orders.close"

# The branch's day rolls over here, not at midnight: a venue serving past 00:00
# is still working the previous business day.
DAY_CLOSE_HOUR = 6


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY, rounding=ROUND_HALF_UP)


class OrderService:
    """Open checks on tables.

    Every write is permission-gated first, then executed. Closing is the one that
    matters most: a check cannot close until its payments cover the total, because
    `venue_daily_stats.revenue` is summed from `order_payments` and a close with no
    payment row would make the dashboard quietly understate the day's takings.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.orders = OrderRepository(session)
        self.tables = VenueTableRepository(session)
        self.menu_items = MenuItemRepository(session)
        self.staff = StaffService(session)
        self.receipts = ReceiptService(session)

    def business_date_for(self, moment: datetime) -> date_type:
        """The branch's day-close rule, not `now().date()`.

        A table opened at 01:30 belongs to the previous business day, which is what
        makes the daily order numbering and the revenue rollup line up with how the
        venue actually counts a night.
        """
        if moment.hour < DAY_CLOSE_HOUR:
            return (moment - timedelta(days=1)).date()
        return moment.date()

    async def open_table(self, staff_user_id: int, venue_id: int, payload: OrderOpen) -> OrderRead:
        await self.staff.require_permission_in_transaction(staff_user_id, venue_id, PERM_OPEN)
        staff_row = await self.staff.employment_for_in_transaction(staff_user_id, venue_id)

        table = await self.tables.get_by_id(payload.table_id)
        if table is None or table.venue_id != venue_id:
            raise NotFoundError("That table does not belong to this venue")

        now = utcnow_naive()
        try:
            order = await self.orders.open_for_table(
                venue_id=venue_id,
                table_id=payload.table_id,
                staff_id=staff_row.id,
                business_date=self.business_date_for(now),
                now=now,
                guests_count=payload.guests_count,
            )
            await self.session.commit()
        except IntegrityError as error:
            # `one_open_order_per_table` — two waiters tapped the same empty table.
            raise translate_integrity_error(error) from error
        return OrderRead.model_validate(order)

    async def board(self, venue_id: int, zone_id: int | None = None) -> Sequence[TableBoardRow]:
        """Every active table with its live order, or none."""
        now = utcnow_naive()
        rows = await self.orders.table_board(venue_id, zone_id)
        return [
            TableBoardRow(
                table_id=row.table.id,
                number=row.table.number,
                seats=row.table.seats,
                zone_id=row.table.zone_id,
                order=(
                    self._to_list_item(row.order, row.table.number, now)
                    if row.order is not None
                    else None
                ),
            )
            for row in rows
        ]

    async def list_for_board(
        self, venue_id: int, statuses: Sequence[str] | None = None
    ) -> Sequence[OrderListItem]:
        now = utcnow_naive()
        rows = await self.orders.list_for_board(venue_id, statuses, self.business_date_for(now))
        return [self._to_list_item(order, None, now) for order in rows]

    async def add_items(
        self,
        staff_user_id: int,
        venue_id: int,
        order_id: int,
        items: Sequence[OrderItemCreate],
        language_id: int,
    ) -> OrderDetailRead:
        """Prices and names are snapshotted at insert.

        Resolving them later would join to live `menu_items` and silently reprice a
        check that a guest has already been shown.
        """
        await self.staff.require_permission_in_transaction(staff_user_id, venue_id, PERM_ADD_ITEMS)
        staff_row = await self.staff.employment_for_in_transaction(staff_user_id, venue_id)

        order = await self._require_open_order(order_id, venue_id)
        now = utcnow_naive()

        rows: list[OrderItem] = []
        for entry in items:
            unit_price = await self.menu_items.resolve_price(
                entry.menu_item_id, venue_id, entry.variant_id
            )
            detail = await self.menu_items.get_with_variants(
                entry.menu_item_id, venue_id, language_id
            )
            name = detail.name if detail is not None else f"#{entry.menu_item_id}"
            variant_name: str | None = None
            if entry.variant_id is not None and detail is not None:
                variant_name = next(
                    (v.name for v in detail.variants if v.variant.id == entry.variant_id),
                    None,
                )
            rows.append(
                OrderItem(
                    menu_item_id=entry.menu_item_id,
                    variant_id=entry.variant_id,
                    quantity=entry.quantity,
                    unit_price=_money(unit_price),
                    discount_amount=Decimal("0"),
                    total_price=_money(unit_price * entry.quantity),
                    name_snapshot=name,
                    variant_name_snapshot=variant_name,
                    status=OrderItemStatus.NEW,
                    note=entry.note,
                    added_by_staff_id=staff_row.id,
                    added_at=now,
                )
            )

        await self.orders.add_items(order.id, rows)
        await self.orders.recalculate_totals(order.id)
        if order.status == OrderStatus.OPEN:
            await self.orders.set_status(order.id, OrderStatus.IN_PROGRESS)
        await self.session.commit()
        return await self.get_detail(order.id, venue_id)

    async def get_detail(self, order_id: int, venue_id: int) -> OrderDetailRead:
        order = await self.orders.get_by_id(order_id)
        if order is None or order.venue_id != venue_id:
            raise NotFoundError("Order not found at this venue")

        items = await self.orders.list_items(order_id)
        payments = await self.orders.list_payments(order_id)
        paid = await self.orders.sum_payments(order_id)
        now = utcnow_naive()

        return OrderDetailRead(
            order=OrderRead.model_validate(order),
            items=[OrderItemRead.model_validate(item) for item in items],
            payments=[OrderPaymentRead.model_validate(row) for row in payments],
            paid_amount=_money(paid),
            elapsed_seconds=self._elapsed(order.opened_at, now),
        )

    async def add_payment(
        self,
        staff_user_id: int,
        venue_id: int,
        order_id: int,
        payload: OrderPaymentCreate,
    ) -> OrderPaymentRead:
        """Split payments are several rows against one order. Cash is valid."""
        await self.staff.require_permission_in_transaction(staff_user_id, venue_id, PERM_CLOSE)
        staff_row = await self.staff.employment_for_in_transaction(staff_user_id, venue_id)
        order = await self._require_open_order(order_id, venue_id)

        payment = await self.orders.add_payment(
            OrderPayment(
                order_id=order.id,
                method=payload.method,
                amount=_money(payload.amount),
                currency=order.currency,
                received_by_staff_id=staff_row.id,
                paid_at=utcnow_naive(),
                provider_transaction_id=payload.provider_transaction_id,
                change_amount=payload.change_amount,
            )
        )
        paid = await self.orders.sum_payments(order.id)
        if paid >= order.total_amount:
            await self.orders.set_status(order.id, OrderStatus.AWAITING_PAYMENT)
        await self.session.commit()
        return OrderPaymentRead.model_validate(payment)

    async def close(self, staff_user_id: int, venue_id: int, order_id: int) -> ReceiptRead:
        """Payments must cover the total, then the receipt is written once.

        This is Part 2's open question 9 settled: a close with no payment row is
        refused, because the dashboard's revenue reads from those rows and would
        otherwise be fiction.
        """
        await self.staff.require_permission_in_transaction(staff_user_id, venue_id, PERM_CLOSE)
        staff_row = await self.staff.employment_for_in_transaction(staff_user_id, venue_id)

        order = await self.orders.get_by_id(order_id)
        if order is None or order.venue_id != venue_id:
            raise NotFoundError("Order not found at this venue")

        paid = await self.orders.sum_payments(order_id)
        if paid < order.total_amount:
            raise PaymentIncompleteError(
                "The check is not fully paid",
                details={
                    "total_amount": str(order.total_amount),
                    "paid_amount": str(paid),
                    "outstanding": str(_money(order.total_amount - paid)),
                },
            )

        items = await self.orders.list_items(order_id)
        payments = await self.orders.list_payments(order_id)
        receipt = await self.receipts.issue_in_transaction(
            order_id,
            staff_row.id,
            payload=self._receipt_payload(order, items, payments),
        )

        closed = await self.orders.close(order_id, staff_row.id, utcnow_naive())
        if closed is None:
            raise ValidationFailedError(
                "This check cannot be closed from its current status",
                details={"status": order.status},
            )
        await self.session.commit()
        return ReceiptRead.model_validate(receipt)

    async def cancel(
        self, staff_user_id: int, venue_id: int, order_id: int, payload: OrderCancel
    ) -> OrderRead:
        await self.staff.require_permission_in_transaction(staff_user_id, venue_id, PERM_CLOSE)
        staff_row = await self.staff.employment_for_in_transaction(staff_user_id, venue_id)
        cancelled = await self.orders.cancel(order_id, staff_row.id, utcnow_naive(), payload.reason)
        if cancelled is None:
            raise NotFoundError("Order not found, or already closed")
        await self.session.commit()
        return OrderRead.model_validate(cancelled)

    async def kitchen_queue(self, venue_id: int) -> Sequence[KitchenQueueItem]:
        rows = await self.orders.kitchen_queue(venue_id)
        return [
            KitchenQueueItem(
                id=row.item.id,
                order_id=row.item.order_id,
                table_number=row.table_number,
                name_snapshot=row.item.name_snapshot,
                variant_name_snapshot=row.item.variant_name_snapshot,
                quantity=row.item.quantity,
                status=OrderItemStatus(row.item.status),
                note=row.item.note,
                added_at=row.item.added_at,
            )
            for row in rows
        ]

    # --- internals -----------------------------------------------------------

    async def _require_open_order(self, order_id: int, venue_id: int) -> Order:
        order = await self.orders.get_by_id(order_id)
        if order is None or order.venue_id != venue_id:
            raise NotFoundError("Order not found at this venue")
        if order.status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED):
            raise ValidationFailedError("This check is already closed")
        return order

    def _elapsed(self, opened_at: datetime, now: datetime) -> int:
        return max(int((now - opened_at).total_seconds()), 0)

    def _to_list_item(self, order: Order, table_number: int | None, now: datetime) -> OrderListItem:
        return OrderListItem(
            id=order.id,
            order_number=order.order_number,
            table_id=order.table_id,
            table_number=table_number,
            status=OrderStatus(order.status),
            kind=OrderKind(order.kind),
            guests_count=order.guests_count,
            total_amount=order.total_amount,
            currency=order.currency,
            opened_at=order.opened_at,
            elapsed_seconds=self._elapsed(order.opened_at, now),
        )

    def _receipt_payload(
        self,
        order: Order,
        items: Sequence[OrderItem],
        payments: Sequence[OrderPayment],
    ) -> dict[str, object]:
        """Frozen print lines. Everything the slip shows, resolved now."""
        return {
            "order_number": order.order_number,
            "business_date": order.business_date.isoformat(),
            "currency": order.currency,
            "subtotal": str(order.subtotal),
            "discount_amount": str(order.discount_amount),
            "service_charge": str(order.service_charge),
            "total_amount": str(order.total_amount),
            "items": [
                {
                    "name": item.name_snapshot,
                    "variant": item.variant_name_snapshot,
                    "quantity": item.quantity,
                    "unit_price": str(item.unit_price),
                    "total_price": str(item.total_price),
                }
                for item in items
                if item.status != OrderItemStatus.CANCELLED
            ],
            "payments": [
                {"method": payment.method, "amount": str(payment.amount)} for payment in payments
            ],
        }
