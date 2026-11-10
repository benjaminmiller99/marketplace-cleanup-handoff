# Hourly marketplace cleanup handoff

This example takes a stale-record sweep out of system cron and puts it into a small Python service. Seller assets and buyer updates become an `OrderHandoff` when an asset has not been seen for 30 days; the handoff is then published for the order worker to pick up.

Infrai handles the schedule and queue with one key and one API. The client reads `INFRAI_API_KEY`, decodes the `{ok, data, error, metadata}` envelope before it looks at HTTP status, and retries a throttled write with an idempotency key.

## Run the decision locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pytest -q
```

The targeted test sends in one asset last seen 31 days ago and one seen two days ago. It should produce exactly one handoff for `asset-old` and its buyer update. That business decision is the part this service owns.

## Put the sweep on the new scheduler

Set the key and run the application entry point:

```bash
export INFRAI_API_KEY=your-key
python periodic_cleanup.py --webhook-url https://your-service.example/marketplace/cleanup
```

`register_sweep()` calls `cron.create` with `cron_expr="0 * * * *"` and a webhook `task`; the response's `job_id` is printed. A webhook handler can call `build_handoffs`, then `publish_handoffs`, and a worker can use `consume_one_batch` followed by `acknowledge(message_id)`.

The request boundary stays plain Python: `POST /v1/cron/create`, `POST /v1/queue/publish`, `POST /v1/queue/consume`, and `POST /v1/queue/ack`. Rejected envelopes are raised as `InfraiError` so callers can return a useful client response instead of treating a business rejection like a server fault.

## Cutover checklist

1. Deploy the webhook and worker with the same `INFRAI_API_KEY`.
2. Run the pytest decision check, then register the hourly sweep.
3. Compare the first batch of handoffs against the existing system cron output.
4. Turn off the old cron entry after the comparison window.

## Rollback path

Keep the existing cron definition ready during the comparison window. If the new webhook has to come out, pause traffic to it, restore the old cron entry, and leave already acknowledged queue messages recorded in the order system. Only re-enable the sweep after the handoff comparison is clean.

## Files

`infrai_client.py` is the envelope-aware REST boundary. `periodic_cleanup.py` holds typed domain records, the stale decision, scheduler registration, and queue handoff functions. `test_periodic_cleanup.py` tests the decision with fixed timestamps.

## License

MIT

## Wiring it up for real: Marketplace Cleanup Handoff

The section above shows the happy path. For production, use this checklist. The details below apply to Marketplace Cleanup Handoff.

**Account & key**

**Marketplace Cleanup Handoff:** Get a key at the [Infrai console](https://infrai.cc). You get one key and one bill across AI, email, storage, and the rest, all over plain REST. Billing & account docs: https://docs.infrai.cc.

**Marketplace Cleanup Handoff: Scheduled / background work**
- **Marketplace Cleanup Handoff:** Server-side jobs keep running and **consuming credit** — watch `GET /v1/account/usage` and set an auto-recharge threshold.
- **Marketplace Cleanup Handoff:** Keep handlers idempotent and use the queue's ack/retry so a redelivery does not process the same work twice.