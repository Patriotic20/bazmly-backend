from typing import Annotated

from fastapi import Depends

from app.core.dependencies import SessionDep
from app.modules.staff.services import StaffService


def get_staff_service(session: SessionDep) -> StaffService:
    return StaffService(session)


StaffServiceDep = Annotated[StaffService, Depends(get_staff_service)]
