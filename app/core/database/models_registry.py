"""
Import all models here so SQLAlchemy's Base.metadata is fully populated.
Used by Alembic env.py and anywhere that needs all tables registered.

Imports are grouped per module, in the same dependency order as the migrations:

    geo → auth → catalog → venue_groups → venues → staff
      → menu → services → bookings → orders
      → reviews → engagement → analytics

Adding a model without registering it here makes it invisible to
`alembic revision --autogenerate`, which then silently emits an empty revision.
"""

from app.modules.analytics.models import VenueDailyStats
from app.modules.auth.models import (
    Device,
    Friendship,
    RefreshToken,
    User,
)
from app.modules.bookings.models import (
    Booking,
    BookingItem,
    BookingPriceLine,
    BookingService,
    BookingStatusHistory,
    VenueBlockedSlot,
)
from app.modules.catalog.models import Amenity
from app.modules.engagement.models import (
    Conversation,
    Favorite,
    Message,
    Notification,
    SearchHistory,
)
from app.modules.geo.models import District, Region, UserRecentLocation
from app.modules.menu.models import (
    MenuCategory,
    MenuItem,
    MenuItemBranch,
    MenuItemVariant,
    MenuItemVariantBranch,
)
from app.modules.orders.models import (
    Order,
    OrderItem,
    OrderPayment,
    OrderStatusHistory,
    Receipt,
)
from app.modules.reviews.models import Review, ReviewPhoto, ReviewReply
from app.modules.services.models import (
    ServiceCatalog,
    VenueService,
    VenueServiceItem,
)
from app.modules.staff.models import (
    Permission,
    StaffInvitation,
    StaffRole,
    StaffRolePermission,
    VenueStaff,
)
from app.modules.venue_groups.models import VenueGroup
from app.modules.venues.models import (
    Venue,
    VenueAmenity,
    VenueGuestTier,
    VenuePhoto,
    VenueSpecialDay,
    VenueTable,
    VenueTableQr,
    VenueWorkingHours,
    VenueZone,
)

__all__ = [
    "Amenity",
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
    "MenuCategory",
    "MenuItem",
    "MenuItemBranch",
    "MenuItemVariant",
    "MenuItemVariantBranch",
    "Message",
    "Notification",
    "Order",
    "OrderItem",
    "OrderPayment",
    "OrderStatusHistory",
    "Permission",
    "Receipt",
    "RefreshToken",
    "Region",
    "Review",
    "ReviewPhoto",
    "ReviewReply",
    "SearchHistory",
    "ServiceCatalog",
    "StaffInvitation",
    "StaffRole",
    "StaffRolePermission",
    "User",
    "UserRecentLocation",
    "Venue",
    "VenueAmenity",
    "VenueBlockedSlot",
    "VenueDailyStats",
    "VenueGroup",
    "VenueGuestTier",
    "VenuePhoto",
    "VenueService",
    "VenueServiceItem",
    "VenueSpecialDay",
    "VenueStaff",
    "VenueTable",
    "VenueTableQr",
    "VenueWorkingHours",
    "VenueZone",
]
