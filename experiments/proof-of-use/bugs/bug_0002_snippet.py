import asyncio

# Runs several account-charge operations concurrently, then must immediately
# reconcile every account's outcome. When one charge fails fast, the slower
# ones are left unfinished at the moment we reconcile.

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
            charge(1, 0.20, outcomes),  # slow
            charge(2, 0.01, outcomes),  # fails FAST
            charge(3, 0.20, outcomes),  # slow
        )
    except ValueError:
        pass  # caught the fast failure

    # Reconcile NOW. Both non-failing accounts must have a known outcome.
    settled = len(outcomes)
    print(f"settled_accounts={settled}")
    print(f"reconciliation_complete={settled == 2}")

asyncio.run(charge_all())
