"""Marketplace cleanup sweep with an explicit migration handoff."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from infrai_client import InfraiClient


@dataclass(frozen=True)
class SellerAsset:
    asset_id: str
    seller_id: str
    last_seen: datetime


@dataclass(frozen=True)
class BuyerUpdate:
    buyer_id: str
    order_id: str
    updated_at: datetime


@dataclass(frozen=True)
class OrderHandoff:
    order_id: str
    seller_id: str
    buyer_id: str
    asset_id: str


def stale(asset: SellerAsset, now: datetime, max_age_days: int) -> bool:
    return now - asset.last_seen >= __import__("datetime").timedelta(days=max_age_days)


def build_handoffs(assets: list[SellerAsset], updates: list[BuyerUpdate], now: datetime,
                   max_age_days: int = 30) -> list[OrderHandoff]:
    buyers = {update.order_id: update.buyer_id for update in updates}
    return [OrderHandoff(order_id=f"cleanup:{asset.asset_id}", seller_id=asset.seller_id,
                         buyer_id=buyers.get(asset.asset_id, "pending"), asset_id=asset.asset_id)
            for asset in assets if stale(asset, now, max_age_days)]


def register_sweep(client: InfraiClient, webhook_url: str) -> str:
    cron_expr = "0 * * * *"
    request_id = "marketplace-cleanup-hourly:" + sha256(
        f"{cron_expr}\n{webhook_url}".encode("utf-8")
    ).hexdigest()
    data = client.cron_create(cron_expr, webhook_url, request_id)
    return str(data["job_id"])


def publish_handoffs(client: InfraiClient, handoffs: list[OrderHandoff]) -> int:
    for handoff in handoffs:
        client.queue_publish({"order_id": handoff.order_id, "seller_id": handoff.seller_id,
                              "buyer_id": handoff.buyer_id, "asset_id": handoff.asset_id},
                             f"handoff:{handoff.asset_id}")
    return len(handoffs)


def consume_one_batch(client: InfraiClient) -> list[dict[str, Any]]:
    data = client.queue_consume(max_messages=10, visibility_timeout=120)
    return list(data.get("items") or [])


def acknowledge(client: InfraiClient, message_id: str) -> None:
    client.queue_ack(message_id)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Register the hourly cleanup sweep.")
    parser.add_argument("--webhook-url", required=True, help="Cleanup webhook destination")
    args = parser.parse_args()
    client = InfraiClient()
    job_id = register_sweep(client, args.webhook_url)
    print(f"registered cleanup sweep {job_id} at {datetime.now(timezone.utc).isoformat()}")
