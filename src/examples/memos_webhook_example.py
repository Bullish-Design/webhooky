#!/usr/bin/env python3
"""
Minimal Memos webhook example for WebHooky.

Defines a typed event for activityType == "memos.memo.created" and demonstrates
dispatching the sample payload through the EventBus.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, List
from pydantic import BaseModel, ConfigDict

# Import from your package
from webhooky.events import WebhookEventBase, on_activity
from webhooky.bus import EventBus


# ---- Typed payloads ---------------------------------------------------------


class Timestamp(BaseModel):
    seconds: int
    model_config = ConfigDict(extra="ignore")


class Memo(BaseModel):
    name: str
    state: int
    creator: str
    content: Optional[str] = None
    snippet: Optional[str] = None

    create_time: Timestamp | Dict[str, Any] | None = None
    update_time: Timestamp | Dict[str, Any] | None = None
    display_time: Timestamp | Dict[str, Any] | None = None

    nodes: List[Any] = []
    visibility: Optional[int] = None
    property: Dict[str, Any] = {}

    model_config = ConfigDict(extra="allow")


class MemosWebhookPayload(BaseModel):
    url: Optional[str] = None
    activityType: str
    creator: str
    memo: Memo
    model_config = ConfigDict(extra="allow")


# ---- Event ------------------------------------------------------------------


class MemosMemoCreatedEvent(WebhookEventBase[MemosWebhookPayload]):
    """Matches only memos.memo.created and exposes a simple handler."""

    @classmethod
    def _transform_raw_data(cls, raw: Dict[str, Any]) -> Dict[str, Any]:
        # Normalize into the field names that WebHooky looks for
        data = dict(raw or {})
        if "activityType" in data:
            data["activity_type"] = data["activityType"]
        return data

    @classmethod
    def matches(cls, raw: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> bool:
        return raw.get("activityType") == "memos.memo.created"

    @on_activity("memos.memo.created")
    async def handle_created(self) -> None:
        memo = self.payload.memo
        print(f"[MEMOS] New memo by {self.payload.creator}: {memo.content!r} ({memo.name})")


# ---- Demo runner ------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    SAMPLE = {
        "url": "https://smee.io/R5LU3BqERxxxxxxx",
        "activityType": "memos.memo.created",
        "creator": "users/1",
        "memo": {
            "name": "memos/dtyUZZ2fU3sgGMbYfX8z5f",
            "state": 1,
            "creator": "users/1",
            "create_time": {"seconds": 1756674863},
            "update_time": {"seconds": 1756674863},
            "display_time": {"seconds": 1756674863},
            "content": "test",
            "nodes": [
                {
                    "type": 2,
                    "Node": {"ParagraphNode": {"children": [{"type": 51, "Node": {"TextNode": {"content": "test"}}}]}},
                }
            ],
            "visibility": 1,
            "property": {},
            "snippet": "test\n",
        },
    }

    async def main():
        bus = EventBus()
        result = await bus.dispatch_raw(SAMPLE, headers={"Content-Type": "application/json"})
        print("success:", result.success, "matched:", result.matched_patterns, "errors:", result.errors)

    asyncio.run(main())
