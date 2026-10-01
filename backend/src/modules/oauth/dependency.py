import logging
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth

security = HTTPBearer()
logger = logging.getLogger(__name__)

# Tolerate small clock drift between this host and Google ("Token used too early").
CLOCK_SKEW_SECONDS = 10


def verify_firebase_token(
    cred: Annotated[HTTPAuthorizationCredentials, Depends(security)],
):
    token = cred.credentials
    try:
        # Decode and verify the ID token using the globally initialized Admin SDK
        decoded_token = auth.verify_id_token(token, clock_skew_seconds=CLOCK_SKEW_SECONDS)
        return decoded_token
    except Exception as exc:
        logger.info("Firebase token rejected: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired Firebase token."
        )