from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database.base import Base
from app.core.database.mixins import IdIntPk, TimestampMixin


class StaffRoleTranslation(IdIntPk, TimestampMixin, Base):
    """Egasi, Admin, Menendjer, Ofitsant, Oshpaz, Oshpaz yordamchisi, Qo'riqchi.

    Role badge colours on the Hodimlar cards are a client concern; not stored.
    """

    __tablename__ = "staff_role_translations"
    __table_args__ = (UniqueConstraint("staff_role_id", "language_id"),)

    staff_role_id: Mapped[int] = mapped_column(
        ForeignKey("staff_roles.id", ondelete="CASCADE"), nullable=False
    )
    language_id: Mapped[int] = mapped_column(ForeignKey("languages.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
