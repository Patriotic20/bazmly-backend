from typing import Annotated

from fastapi import Depends

from app.core.dependencies import SessionDep
from app.modules.menu.services import MenuService


def get_menu_service(session: SessionDep) -> MenuService:
    return MenuService(session)


MenuServiceDep = Annotated[MenuService, Depends(get_menu_service)]
