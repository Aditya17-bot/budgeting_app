import os
from typing import Optional

from fastapi import Header, HTTPException, status


def verify_internal_webhook_token(x_webhook_token: Optional[str] = Header(default=None)) -> None:
    expected_token = os.getenv("WEBHOOK_TOKEN")
    if not expected_token:
        return
    if x_webhook_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook token",
        )
