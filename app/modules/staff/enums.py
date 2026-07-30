"""Enum values for the `staff` module.

Re-exported from the model files that declare them, so models and schemas
share one object per enum. Schemas import from here; nothing redeclares an
enum. See DECISIONS.md for why the declarations still sit in the models.
"""

from app.modules.staff.models.staff_role import StaffRoleScope

__all__ = [
    "StaffRoleScope",
]
