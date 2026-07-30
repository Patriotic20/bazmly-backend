"""Validation order, the per-user limit, and the discount ceiling."""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database.mixins import utcnow_naive
from app.core.exceptions import PromoCodeExhaustedError, PromoCodeInvalidError
from app.modules.promotions.enums import DiscountType, PromoAppliesTo
from app.modules.promotions.models import PromoCode
from app.modules.promotions.services import PromoCodeService
from tests.repositories import factories

SUBTOTAL = Decimal("500000.00")


async def make_code(
    session: AsyncSession,
    *,
    discount_type: str = DiscountType.PERCENT,
    value: Decimal = Decimal("20"),
    max_discount: Decimal | None = None,
    usage_limit_total: int | None = None,
    usage_limit_per_user: int = 1,
    used_count: int = 0,
    min_amount: Decimal | None = None,
    is_active: bool = True,
    expired: bool = False,
) -> PromoCode:
    now = utcnow_naive()
    code = PromoCode(
        code=f"SAVE{factories.unique_suffix().upper()[:6]}",
        discount_type=discount_type,
        value=value,
        applies_to=PromoAppliesTo.BOTH,
        min_amount=min_amount,
        max_discount=max_discount,
        usage_limit_total=usage_limit_total,
        usage_limit_per_user=usage_limit_per_user,
        used_count=used_count,
        valid_from=now - timedelta(days=1),
        valid_to=now - timedelta(hours=1) if expired else now + timedelta(days=30),
        is_active=is_active,
    )
    session.add(code)
    await session.flush()
    return code


async def test_percentage_discount_is_capped_by_max_discount(
    session: AsyncSession,
) -> None:
    """A 20% code with a 50 000 ceiling gives 50 000, not 100 000.

    Without the cap, one large booking could absorb an entire campaign budget.
    """
    user = await factories.make_user(session)
    code = await make_code(session, value=Decimal("20"), max_discount=Decimal("50000.00"))

    preview = await PromoCodeService(session).preview(user.id, code.code, SUBTOTAL)

    assert preview.discount_amount == Decimal("50000.00")
    assert preview.total_after_discount == Decimal("450000.00")


async def test_percentage_discount_without_a_cap_is_the_full_percentage(
    session: AsyncSession,
) -> None:
    user = await factories.make_user(session)
    code = await make_code(session, value=Decimal("20"))

    preview = await PromoCodeService(session).preview(user.id, code.code, SUBTOTAL)

    assert preview.discount_amount == Decimal("100000.00")


async def test_discount_never_exceeds_the_subtotal(session: AsyncSession) -> None:
    """A fixed code worth more than the order does not produce a negative total."""
    user = await factories.make_user(session)
    code = await make_code(session, discount_type=DiscountType.FIXED, value=Decimal("900000.00"))

    preview = await PromoCodeService(session).preview(user.id, code.code, SUBTOTAL)

    assert preview.discount_amount == SUBTOTAL
    assert preview.total_after_discount == Decimal("0.00")


async def test_per_user_limit_is_enforced(session: AsyncSession) -> None:
    """The redemption row, not the global counter, is what bounds one person."""
    user = await factories.make_user(session)
    code = await make_code(session, usage_limit_per_user=1)
    service = PromoCodeService(session)

    application = await service.apply_in_transaction(user.id, code.code, SUBTOTAL)
    await service.record_redemption_in_transaction(application, user.id)
    await session.flush()

    with pytest.raises(PromoCodeExhaustedError):
        await service.apply_in_transaction(user.id, code.code, SUBTOTAL)


async def test_another_user_is_unaffected_by_the_first_users_limit(
    session: AsyncSession,
) -> None:
    first = await factories.make_user(session)
    second = await factories.make_user(session)
    code = await make_code(session, usage_limit_per_user=1)
    service = PromoCodeService(session)

    application = await service.apply_in_transaction(first.id, code.code, SUBTOTAL)
    await service.record_redemption_in_transaction(application, first.id)
    await session.flush()

    # The campaign is per-user limited, not single-use overall.
    second_application = await service.apply_in_transaction(second.id, code.code, SUBTOTAL)
    assert second_application.discount_amount > 0


async def test_exhausted_code_raises(session: AsyncSession) -> None:
    user = await factories.make_user(session)
    code = await make_code(session, usage_limit_total=5, used_count=5)

    with pytest.raises(PromoCodeExhaustedError):
        await PromoCodeService(session).preview(user.id, code.code, SUBTOTAL)


async def test_inactive_expired_and_below_minimum_are_all_invalid(
    session: AsyncSession,
) -> None:
    """Each failure has its own reason, checked in a fixed order."""
    user = await factories.make_user(session)
    service = PromoCodeService(session)

    inactive = await make_code(session, is_active=False)
    with pytest.raises(PromoCodeInvalidError):
        await service.preview(user.id, inactive.code, SUBTOTAL)

    expired = await make_code(session, expired=True)
    with pytest.raises(PromoCodeInvalidError):
        await service.preview(user.id, expired.code, SUBTOTAL)

    too_small = await make_code(session, min_amount=Decimal("1000000.00"))
    with pytest.raises(PromoCodeInvalidError):
        await service.preview(user.id, too_small.code, SUBTOTAL)


async def test_unknown_code_is_invalid(session: AsyncSession) -> None:
    user = await factories.make_user(session)

    with pytest.raises(PromoCodeInvalidError):
        await PromoCodeService(session).preview(user.id, "NOSUCHCODE", SUBTOTAL)


async def test_code_lookup_is_case_insensitive(session: AsyncSession) -> None:
    """The schema upper-cases input, and the lookup is case-insensitive anyway."""
    user = await factories.make_user(session)
    code = await make_code(session)

    preview = await PromoCodeService(session).preview(user.id, code.code.lower(), SUBTOTAL)

    assert preview.code == code.code
