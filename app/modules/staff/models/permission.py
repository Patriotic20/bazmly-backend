from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class Permission(IdIntPk, TimestampMixin, Base):
    """ "Menejer filialni to'liq boshqarish huquqiga ega bo'ladi" as rows.

    Written as rows it is checkable at the API layer and editable without a deploy.
    """

    __tablename__ = "permissions"

    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    group: Mapped[str] = mapped_column(String(50), nullable=False)
