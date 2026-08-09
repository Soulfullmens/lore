import asyncio

# Reads rows from a database cursor (async generator) and returns the first
# matching row. The cursor appends to conn_log when its connection opens/closes.
# find_first returns (row, conn_log) — the caller inspects conn_log.

async def query_rows(conn_log):
    conn_log.append("open")
    try:
        for row in [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}, {"id": 3, "name": "carol"}]:
            yield row
    finally:
        conn_log.append("close")

async def find_first(target_name):
    conn_log = []
    matched = None
    async for row in query_rows(conn_log):
        if row["name"] == target_name:
            matched = row
            break
    return matched, list(conn_log)   # snapshot at return time
