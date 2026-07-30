"""Payment provider callbacks.

Deliberately outside the versioned tree and outside the standard error envelope.
Payme and Click each expect their own response shape, and a gateway that does not
recognise what it gets back retries forever — so these routes answer in the
provider's vocabulary, not ours.

No JWT: the caller is a server, authenticated by an HMAC over the raw body.
Handled here rather than by a global exception handler, because the response body
for a failure is provider-specific.
"""

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request

from app.core.config import settings
from app.core.dependencies import SessionDep
from app.core.exceptions import NotFoundError
from app.core.webhooks.signatures import verify_signature
from app.modules.payments.services import PaymentService

logger = logging.getLogger("app.webhooks")

router = APIRouter(prefix="/v1/webhooks", tags=["webhooks"])

# Payme's JSON-RPC error codes.
PAYME_ERR_UNAUTHORIZED = -32504
PAYME_ERR_TRANSACTION_NOT_FOUND = -31003

# Click's own numbering.
CLICK_ERR_SIGN_CHECK_FAILED = -1
CLICK_ERR_TRANSACTION_NOT_FOUND = -5


async def _settle(session: SessionDep, provider: str, transaction_id: str, succeeded: bool) -> bool:
    """Idempotent by construction — the service looks the payment up by
    `(provider, provider_transaction_id)`, so a replayed callback settles nothing
    twice.

    The `NotFoundError` is caught here rather than by a global handler because the
    "unknown transaction" reply has to be phrased in the provider's own vocabulary.
    """
    try:
        await PaymentService(session).settle_webhook(provider, transaction_id, succeeded)
    except NotFoundError:
        return False
    return True


@router.post(
    "/payme",
    response_model=dict[str, Any],
    operation_id="webhooks_payme",
    summary="Payme callback",
    description="HMAC-verified, idempotent on provider_transaction_id. Answers JSON-RPC.",
)
async def payme(
    request: Request,
    session: SessionDep,
    x_signature: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    body = await request.body()
    if not verify_signature(body, x_signature, settings.webhooks.payme_secret):
        logger.warning("Payme callback rejected: bad signature")
        return {"error": {"code": PAYME_ERR_UNAUTHORIZED, "message": "Invalid signature"}}

    payload = await request.json()
    params = payload.get("params", {})
    transaction_id = str(params.get("id", ""))
    settled = await _settle(session, "payme", transaction_id, params.get("state", 2) == 2)

    if not settled:
        return {
            "error": {
                "code": PAYME_ERR_TRANSACTION_NOT_FOUND,
                "message": "Transaction not found",
            }
        }
    return {"result": {"state": 2}}


@router.post(
    "/click",
    response_model=dict[str, Any],
    operation_id="webhooks_click",
    summary="Click callback",
    description="HMAC-verified, idempotent on provider_transaction_id. Answers Click's envelope.",
)
async def click(
    request: Request,
    session: SessionDep,
    x_signature: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    body = await request.body()
    if not verify_signature(body, x_signature, settings.webhooks.click_secret):
        logger.warning("Click callback rejected: bad signature")
        return {"error": CLICK_ERR_SIGN_CHECK_FAILED, "error_note": "SIGN CHECK FAILED"}

    payload = await request.json()
    transaction_id = str(payload.get("click_trans_id", ""))
    settled = await _settle(session, "click", transaction_id, int(payload.get("error", 0)) == 0)

    if not settled:
        return {"error": CLICK_ERR_TRANSACTION_NOT_FOUND, "error_note": "Transaction not found"}
    return {"error": 0, "error_note": "Success"}
