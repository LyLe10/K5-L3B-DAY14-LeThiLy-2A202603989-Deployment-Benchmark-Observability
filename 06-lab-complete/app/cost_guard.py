from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from app.config import settings
from app.redis_client import r

# Prices in billionths of a dollar per token, so Redis can account in integers.
INPUT_TOKEN_PRICE = 150
OUTPUT_TOKEN_PRICE = 600
NANOUSD_PER_USD = 1_000_000_000

charge_budget = r.register_script("""
local cost = tonumber(ARGV[1])
for i, key in ipairs(KEYS) do
    local spent = tonumber(redis.call('GET', key) or '0')
    local limit = tonumber(ARGV[i + 1])
    if spent >= limit or spent + cost > limit then return 0 end
end
if cost > 0 then
    for i, key in ipairs(KEYS) do
        redis.call('INCRBY', key, cost)
        redis.call('EXPIREAT', key, ARGV[i + 3])
    end
end
return 1
""")


def _apply_budget(cost: int) -> None:
    now = datetime.now(timezone.utc)
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    next_month = (now.replace(day=1) + timedelta(days=32)).replace(
        day=1, hour=0, minute=0, second=0, microsecond=0
    )
    allowed = charge_budget(
        keys=[f"part6:budget:{now:%Y-%m-%d}", f"part6:budget:{now:%Y-%m}"],
        args=[
            cost,
            int(settings.daily_budget_usd * NANOUSD_PER_USD),
            int(settings.monthly_budget_usd * NANOUSD_PER_USD),
            int(tomorrow.timestamp()),
            int(next_month.timestamp()),
        ],
    )
    if not allowed:
        raise HTTPException(status_code=402, detail="Budget exceeded")


def check_budget() -> None:
    _apply_budget(0)


def record_cost(input_tokens: int, output_tokens: int) -> None:
    _apply_budget(input_tokens * INPUT_TOKEN_PRICE + output_tokens * OUTPUT_TOKEN_PRICE)
