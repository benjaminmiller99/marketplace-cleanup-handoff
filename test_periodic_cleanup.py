from datetime import datetime, timedelta, timezone

from periodic_cleanup import BuyerUpdate, SellerAsset, build_handoffs, register_sweep
from unittest.mock import Mock


def test_registration_key_is_stable_and_distinguishes_webhooks():
    client = Mock()
    client.cron_create.return_value = {"job_id": "test-job"}
    assert register_sweep(client, "https://example.com/cleanup-a") == "test-job"
    register_sweep(client, "https://example.com/cleanup-a")
    register_sweep(client, "https://example.com/cleanup-b")
    first, retry, different = client.cron_create.call_args_list
    assert first == retry
    assert first.args[2] != different.args[2]
    assert first.args[:2] == ("0 * * * *", "https://example.com/cleanup-a")


def test_only_stale_assets_create_order_handoffs():
    now = datetime(2026, 1, 31, tzinfo=timezone.utc)
    assets = [
        SellerAsset("asset-old", "seller-a", now - timedelta(days=31)),
        SellerAsset("asset-fresh", "seller-b", now - timedelta(days=2)),
    ]
    updates = [BuyerUpdate("buyer-a", "asset-old", now)]

    result = build_handoffs(assets, updates, now)

    assert result == [
        __import__("periodic_cleanup").OrderHandoff("cleanup:asset-old", "seller-a", "buyer-a", "asset-old")
    ]
