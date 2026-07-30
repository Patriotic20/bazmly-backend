"""Enum values for the `promotions` module.

Re-exported from the model files that declare them, so models and schemas
share one object per enum. Schemas import from here; nothing redeclares an
enum. See DECISIONS.md for why the declarations still sit in the models.
"""

from app.modules.promotions.models.banner import BannerTargetType
from app.modules.promotions.models.promo_code import DiscountType, PromoAppliesTo
from app.modules.promotions.models.user_promo_code import UserPromoCodeSource, UserPromoCodeStatus

__all__ = [
    "BannerTargetType",
    "DiscountType",
    "PromoAppliesTo",
    "UserPromoCodeSource",
    "UserPromoCodeStatus",
]
