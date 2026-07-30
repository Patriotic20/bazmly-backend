from typing import Annotated

from fastapi import Depends

from app.core.dependencies import SessionDep
from app.modules.orders.services import OrderService, ReceiptService


def get_order_service(session: SessionDep) -> OrderService:
    return OrderService(session)


def get_receipt_service(session: SessionDep) -> ReceiptService:
    return ReceiptService(session)


OrderServiceDep = Annotated[OrderService, Depends(get_order_service)]
ReceiptServiceDep = Annotated[ReceiptService, Depends(get_receipt_service)]
