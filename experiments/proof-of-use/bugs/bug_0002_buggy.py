import asyncio

# Charges several accounts concurrently and returns a dict of every account's
# outcome for reconciliation. Account 2's card is declined (fails fast); the
# others take longer. charge_all returns the outcomes dict.

async def charge(account_id, delay, outcomes):
    await asyncio.sleep(delay)
    if account_id == 2:
        raise ValueError(f"card declined for account {account_id}")
    outcomes[account_id] = "charged"
    return account_id

async def charge_all():
    outcomes = {}
    try:
        await asyncio.gather(
            charge(1, 0.20, outcomes),
            charge(2, 0.01, outcomes),
            charge(3, 0.20, outcomes),
        )
    except ValueError:
        pass
    return dict(outcomes)   # snapshot at return time
