"""Track per-user monthly estimated spending in Redis."""

import os
from datetime import datetime
from decimal import Decimal, localcontext

from redis import Redis
from redis.exceptions import ConnectionError, TimeoutError, WatchError


MONTHLY_BUDGET = Decimal("10")
TTL_SECONDS = 32 * 24 * 60 * 60
_redis = Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def _current_month() -> str:
    return datetime.now().strftime("%Y-%m")


def check_budget(user_id: str, estimated_cost: float) -> bool:
    """Charge the estimate and refresh expiry if it fits the monthly budget."""
    cost = Decimal(str(estimated_cost))
    if not cost.is_finite() or cost < 0:
        raise ValueError("estimated_cost must be finite and nonnegative")

    key = f"budget:{user_id}:{_current_month()}"
    with _redis.pipeline() as transaction:
        while True:
            try:
                transaction.watch(key)
                stored = transaction.get(key)
                if isinstance(stored, bytes):
                    stored = stored.decode("ascii")
                current = Decimal(stored or "0")
                with localcontext() as context:
                    # Two whole digits plus 324 places cover tiny float estimates.
                    context.prec = 326
                    total = current + cost
                if total > MONTHLY_BUDGET:
                    return False

                transaction.multi()
                transaction.set(key, str(total), ex=TTL_SECONDS)
                transaction.execute()
                return True
            except WatchError as error:
                # redis-py also raises WatchError if a watched connection dies.
                # An interrupted EXEC may already have applied the charge.
                if isinstance(error.__context__, (ConnectionError, TimeoutError)):
                    raise
