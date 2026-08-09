import asyncio

# Reads rows from a "database cursor" (async generator). The cursor must
# release its connection when we stop reading. We only need the first match.

async def query_rows(conn_log):
    conn_log.append("connection opened")
    try:
        for row in [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}, {"id": 3, "name": "carol"}]:
            yield row
    finally:
        conn_log.append("connection closed")

async def find_first(target_name):
    conn_log = []
    async for row in query_rows(conn_log):
        if row["name"] == target_name:
            break
    # We are done with the cursor here; the connection should be released.
    print(f"connection_closed_after_use={'connection closed' in conn_log}")
    return conn_log

asyncio.run(find_first("alice"))
