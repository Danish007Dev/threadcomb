import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def watch_invoice_payments(db):
    """
    MongoDB Change Stream: watches invoices collection for status changes to "paid".
    When an invoice is paid, updates brand payment_intelligence with actual payment days.
    This is Loop 2 (per-outcome learning) from the architecture spec.
    Run this as a long-running background task at app startup.
    """
    pipeline = [
        {
            "$match": {
                "operationType": "update",
                "updateDescription.updatedFields.status": "paid",
            }
        }
    ]

    try:
        async with db.invoices.watch(pipeline) as stream:
            async for change in stream:
                try:
                    invoice_id = change["documentKey"]["_id"]
                    invoice = await db.invoices.find_one({"_id": invoice_id})
                    if not invoice:
                        continue

                    # Calculate actual payment days
                    invoice_date = invoice.get("invoice_date") or invoice.get("created_at")
                    paid_date = invoice.get("paid_date") or datetime.utcnow()
                    if invoice_date:
                        payment_days = (paid_date - invoice_date).days
                    else:
                        payment_days = None

                    brand_id = invoice.get("brand_id")
                    if brand_id and payment_days is not None:
                        # Update brand with running average payment days
                        brand = await db.brands.find_one({"_id": brand_id})
                        if brand:
                            existing_avg = brand.get("payment_intelligence", {}).get("avg_payment_days")
                            total_paid = brand.get("payment_intelligence", {}).get("paid_count", 0)

                            if existing_avg and total_paid > 0:
                                new_avg = (existing_avg * total_paid + payment_days) / (total_paid + 1)
                            else:
                                new_avg = payment_days

                            new_reliability = min(
                                (total_paid + 1) / max((total_paid + 1) + brand.get("payment_intelligence", {}).get("overdue_count", 0), 1),
                                1.0
                            )

                            await db.brands.update_one(
                                {"_id": brand_id},
                                {
                                    "$set": {
                                        "payment_intelligence.avg_payment_days": round(new_avg, 1),
                                        "payment_intelligence.payment_reliability": round(new_reliability, 3),
                                        "updated_at": datetime.utcnow(),
                                    },
                                    "$inc": {"payment_intelligence.paid_count": 1},
                                }
                            )
                            logger.info(f"Brand {brand_id} payment intelligence updated. Avg days: {new_avg:.1f}")

                except Exception as e:
                    logger.error(f"Change stream processing error: {e}")
                    continue

    except Exception as e:
        logger.error(f"Change stream watcher died: {e}. Restarting in 30s.")
        await asyncio.sleep(30)
        asyncio.create_task(watch_invoice_payments(db))  # restart


async def start_change_streams(db):
    """Called at app startup to start all change stream watchers."""
    asyncio.create_task(watch_invoice_payments(db))
    logger.info("Change stream watchers started.")
