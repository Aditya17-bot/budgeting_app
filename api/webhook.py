from datetime import datetime
from typing import Any, Dict

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request

from api.auth import verify_internal_webhook_token
from core.parser import process_single_sms
from db.session import DataPersistence

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
db = DataPersistence()


def _normalize_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    body = payload.get("Body") or payload.get("body") or payload.get("message")
    sender = payload.get("From") or payload.get("from") or payload.get("sender")
    message_id = payload.get("MessageSid") or payload.get("message_sid") or payload.get("id")
    received_at = (
        payload.get("Timestamp")
        or payload.get("timestamp")
        or payload.get("date")
        or payload.get("received_at")
        or datetime.utcnow().isoformat()
    )
    return {
        "body": body,
        "sender": sender,
        "message_id": message_id,
        "received_at": received_at,
    }


@router.post("/sms")
async def ingest_sms_webhook(
    request: Request,
    _: None = Depends(verify_internal_webhook_token),
):
    content_type = request.headers.get("content-type", "")

    if "application/json" in content_type:
        raw_payload = await request.json()
    else:
        form_data = await request.form()
        raw_payload = dict(form_data)

    payload = _normalize_payload(raw_payload)
    if not payload["body"]:
        raise HTTPException(status_code=400, detail="Missing SMS body")

    processed = process_single_sms(
        message=payload["body"],
        message_date=payload["received_at"],
        sender=payload["sender"],
    )
    if processed.empty:
        return {
            "accepted": False,
            "saved": 0,
            "message": "SMS received but no financial transaction was detected.",
            "message_id": payload["message_id"],
        }

    saved_total = db.save_transactions(processed)
    row = processed.iloc[0].to_dict()
    if isinstance(row.get("date"), pd.Timestamp):
        row["date"] = row["date"].isoformat()

    return {
        "accepted": True,
        "saved": int(len(processed)),
        "total_in_db": int(saved_total),
        "message_id": payload["message_id"],
        "transaction": row,
    }
