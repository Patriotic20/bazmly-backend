"""Buyurtmalar — staff only.

There is no customer tree here: an order is an open check on a table, written by
staff. The guest's side of the same visit is a booking.
"""

from collections.abc import Sequence
from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from app.core.dependencies import CurrentUser, LanguageId, require_permission
from app.modules.orders.api.dependencies import OrderServiceDep, ReceiptServiceDep
from app.modules.orders.enums import OrderStatus
from app.modules.orders.schemas import (
    KitchenQueueItem,
    OrderCancel,
    OrderDetailRead,
    OrderItemCreate,
    OrderListItem,
    OrderOpen,
    OrderPaymentCreate,
    OrderPaymentRead,
    OrderRead,
    ReceiptRead,
    TableBoardRow,
)

router = APIRouter(prefix="/v1/venue/orders", tags=["venue:orders"])


@router.get(
    "/table-board",
    response_model=list[TableBoardRow],
    operation_id="venue_orders_table_board",
    summary="Stollar board",
    description="Every active table with its live check, or none. Free tables are included.",
)
async def table_board(
    user: CurrentUser,
    service: OrderServiceDep,
    venue_id: Annotated[int, Query(ge=1)],
    zone_id: Annotated[int | None, Query(ge=1)] = None,
) -> Sequence[TableBoardRow]:
    return await service.board(venue_id, zone_id)


@router.get(
    "/kitchen-queue",
    response_model=list[KitchenQueueItem],
    operation_id="venue_orders_kitchen_queue",
    summary="Kitchen queue",
    description="Oshpaz's dish queue, oldest first, with the table number to call out.",
)
async def kitchen_queue(
    user: CurrentUser,
    service: OrderServiceDep,
    venue_id: Annotated[int, Query(ge=1)],
) -> Sequence[KitchenQueueItem]:
    return await service.kitchen_queue(venue_id)


@router.get(
    "",
    response_model=list[OrderListItem],
    operation_id="venue_orders_list",
    summary="List checks",
    description="Buyurtmalar for today's business date, filtered by status chips.",
)
async def list_orders(
    user: CurrentUser,
    service: OrderServiceDep,
    venue_id: Annotated[int, Query(ge=1)],
    statuses: Annotated[list[OrderStatus] | None, Query()] = None,
) -> Sequence[OrderListItem]:
    return await service.list_for_board(venue_id, statuses)


@router.post(
    "",
    response_model=OrderRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="venue_orders_open_table",
    summary="Open a table",
    description="Two waiters tapping the same table produce one check and one 409.",
    dependencies=[require_permission("orders.open")],
)
async def open_table(
    payload: OrderOpen,
    user: CurrentUser,
    service: OrderServiceDep,
    venue_id: Annotated[int, Query(ge=1)],
) -> OrderRead:
    return await service.open_table(user.id, venue_id, payload)


@router.get(
    "/{order_id}",
    response_model=OrderDetailRead,
    operation_id="venue_orders_get_detail",
    summary="Check detail",
    description="Items, payments and the elapsed timer, computed at read.",
)
async def get_detail(
    user: CurrentUser,
    service: OrderServiceDep,
    order_id: Annotated[int, Path(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
) -> OrderDetailRead:
    return await service.get_detail(order_id, venue_id)


@router.post(
    "/{order_id}/items",
    response_model=OrderDetailRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="venue_orders_add_items",
    summary="Add items to a check",
    description="Qo'shish. Prices and names are snapshotted at insert.",
    dependencies=[require_permission("orders.add_items")],
)
async def add_items(
    payload: list[OrderItemCreate],
    user: CurrentUser,
    language_id: LanguageId,
    service: OrderServiceDep,
    order_id: Annotated[int, Path(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
) -> OrderDetailRead:
    return await service.add_items(user.id, venue_id, order_id, payload, language_id)


@router.post(
    "/{order_id}/payments",
    response_model=OrderPaymentRead,
    status_code=status.HTTP_201_CREATED,
    operation_id="venue_orders_add_payment",
    summary="Record a payment",
    description="Split payments are several rows. Cash is a valid method.",
    dependencies=[require_permission("orders.close")],
)
async def add_payment(
    payload: OrderPaymentCreate,
    user: CurrentUser,
    service: OrderServiceDep,
    order_id: Annotated[int, Path(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
) -> OrderPaymentRead:
    return await service.add_payment(user.id, venue_id, order_id, payload)


@router.post(
    "/{order_id}/close",
    response_model=ReceiptRead,
    operation_id="venue_orders_close",
    summary="Close a check and print",
    description="Yakunlash. Refused with 422 until payments cover the total.",
    dependencies=[require_permission("orders.close")],
)
async def close_order(
    user: CurrentUser,
    service: OrderServiceDep,
    order_id: Annotated[int, Path(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
) -> ReceiptRead:
    return await service.close(user.id, venue_id, order_id)


@router.post(
    "/{order_id}/cancel",
    response_model=OrderRead,
    operation_id="venue_orders_cancel",
    summary="Cancel a check",
    description="Voids an open check and records who did it.",
    dependencies=[require_permission("orders.close")],
)
async def cancel_order(
    payload: OrderCancel,
    user: CurrentUser,
    service: OrderServiceDep,
    order_id: Annotated[int, Path(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
) -> OrderRead:
    return await service.cancel(user.id, venue_id, order_id, payload)


@router.get(
    "/{order_id}/receipt",
    response_model=ReceiptRead,
    operation_id="venue_orders_get_receipt",
    summary="Get the receipt",
    description="The frozen payload, identical to what was printed.",
)
async def get_receipt(
    user: CurrentUser,
    service: ReceiptServiceDep,
    order_id: Annotated[int, Path(ge=1)],
) -> ReceiptRead:
    return await service.get_for_order(order_id)


@router.post(
    "/{order_id}/receipt/reprint",
    response_model=ReceiptRead,
    operation_id="venue_orders_reprint_receipt",
    summary="Reprint the receipt",
    description="Increments the counter and changes nothing else.",
    dependencies=[require_permission("orders.close")],
)
async def reprint_receipt(
    user: CurrentUser,
    service: ReceiptServiceDep,
    order_id: Annotated[int, Path(ge=1)],
    venue_id: Annotated[int, Query(ge=1)],
) -> ReceiptRead:
    return await service.reprint(order_id)
