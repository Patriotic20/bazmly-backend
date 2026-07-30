"""
Import all models here so SQLAlchemy's Base.metadata is fully populated.
Used by Alembic env.py and anywhere that needs all tables registered.

Imports are grouped per module, in the same dependency order as the migrations:

    localization → geo → auth → catalog → venue_groups → venues → staff
      → menu → services → promotions → subscriptions → bookings → orders
      → payments → reviews → engagement → analytics

Adding a model without registering it here makes it invisible to
`alembic revision --autogenerate`, which then silently emits an empty revision.
"""

from app.modules.analytics.models import VenueDailyStats
from app.modules.auth.models import (
    AuthIdentity,
    Device,
    Friendship,
    RefreshToken,
    User,
    VerificationCode,
)
from app.modules.bookings.models import (
    Booking,
    BookingItem,
    BookingPriceLine,
    BookingService,
    BookingStatusHistory,
    VenueBlockedSlot,
)
from app.modules.catalog.models import (
    Amenity,
    AmenityTranslation,
    VenueType,
    VenueTypeTranslation,
)
from app.modules.engagement.models import (
    Conversation,
    Favorite,
    Message,
    Notification,
    SearchHistory,
)
from app.modules.geo.models import District, Region, UserRecentLocation
from app.modules.localization.models import Language
from app.modules.menu.models import (
    MenuCategory,
    MenuCategoryTranslation,
    MenuItem,
    MenuItemBranch,
    MenuItemTranslation,
    MenuItemVariant,
    MenuItemVariantBranch,
    MenuItemVariantTranslation,
)
from app.modules.orders.models import (
    Order,
    OrderItem,
    OrderPayment,
    OrderStatusHistory,
    Receipt,
)
from app.modules.payments.models import Payment, PaymentCard, Refund
from app.modules.promotions.models import (
    Banner,
    BannerTranslation,
    PromoCode,
    PromoCodeRedemption,
    UserPromoCode,
)
from app.modules.reviews.models import Review, ReviewPhoto, ReviewReply
from app.modules.services.models import (
    ServiceCatalog,
    ServiceCatalogTranslation,
    VenueService,
    VenueServiceItem,
)
from app.modules.staff.models import (
    Permission,
    StaffInvitation,
    StaffRole,
    StaffRolePermission,
    StaffRoleTranslation,
    VenueStaff,
)
from app.modules.subscriptions.models import (
    SubscriptionPlan,
    SubscriptionPlanTranslation,
    UserSubscription,
)
from app.modules.venue_groups.models import VenueGroup, VenueGroupTranslation
from app.modules.venues.models import (
    Venue,
    VenueAmenity,
    VenueGuestTier,
    VenuePhoto,
    VenueSpecialDay,
    VenueTable,
    VenueTableQr,
    VenueTranslation,
    VenueVenueType,
    VenueWorkingHours,
    VenueZone,
    VenueZoneTranslation,
)

__all__ = [
    "Amenity",
    "AmenityTranslation",
    "AuthIdentity",
    "Banner",
    "BannerTranslation",
    "Booking",
    "BookingItem",
    "BookingPriceLine",
    "BookingService",
    "BookingStatusHistory",
    "Conversation",
    "Device",
    "District",
    "Favorite",
    "Friendship",
    "Language",
    "MenuCategory",
    "MenuCategoryTranslation",
    "MenuItem",
    "MenuItemBranch",
    "MenuItemTranslation",
    "MenuItemVariant",
    "MenuItemVariantBranch",
    "MenuItemVariantTranslation",
    "Message",
    "Notification",
    "Order",
    "OrderItem",
    "OrderPayment",
    "OrderStatusHistory",
    "Payment",
    "PaymentCard",
    "Permission",
    "PromoCode",
    "PromoCodeRedemption",
    "Receipt",
    "RefreshToken",
    "Refund",
    "Region",
    "Review",
    "ReviewPhoto",
    "ReviewReply",
    "SearchHistory",
    "ServiceCatalog",
    "ServiceCatalogTranslation",
    "StaffInvitation",
    "StaffRole",
    "StaffRolePermission",
    "StaffRoleTranslation",
    "SubscriptionPlan",
    "SubscriptionPlanTranslation",
    "User",
    "UserPromoCode",
    "UserRecentLocation",
    "UserSubscription",
    "Venue",
    "VenueAmenity",
    "VenueBlockedSlot",
    "VenueDailyStats",
    "VenueGroup",
    "VenueGroupTranslation",
    "VenueGuestTier",
    "VenuePhoto",
    "VenueService",
    "VenueServiceItem",
    "VenueSpecialDay",
    "VenueStaff",
    "VenueTable",
    "VenueTableQr",
    "VenueTranslation",
    "VenueType",
    "VenueTypeTranslation",
    "VenueVenueType",
    "VenueWorkingHours",
    "VenueZone",
    "VenueZoneTranslation",
    "VerificationCode",
]
