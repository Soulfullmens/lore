"""Probe script to test gemini-3.1-flash-lite on 3 genuinely post-cutoff / recent gotchas (Python 3.13+, Pydantic 2.10+, FastMCP).
Checks whether the model fails cold on these recent behaviors.
"""

from gemini_agent import call_agent

# Probe 1: Python 3.13 asyncio.Queue.shutdown() gotcha
PROBE_1_QUEUE = """In Python 3.13, I added queue.shutdown() to stop my worker loop. But when I run this, the worker loops endlessly spinning CPU instead of exiting cleanly. Fix it.

import asyncio

async def worker(q: asyncio.Queue):
    while True:
        try:
            item = await q.get()
            print("got", item)
            q.task_done()
        except asyncio.QueueEmpty:
            break

async def main():
    q = asyncio.Queue()
    await q.put(1)
    await q.put(2)
    q.shutdown()
    await worker(q)

asyncio.run(main())
"""

# Probe 2: Pydantic defer_build=True gotcha
PROBE_2_PYDANTIC_DEFER = """I set defer_build=True on my Pydantic model for performance, but instantiating User() raises `PydanticUserError: Model 'User' is not fully defined`. Fix it while keeping defer_build=True.

from pydantic import BaseModel, ConfigDict

class User(BaseModel):
    model_config = ConfigDict(defer_build=True)
    id: int
    name: str = "guest"

u = User(id=1)
print(u)
"""

# Probe 3: FastMCP Context gotcha
PROBE_3_FASTMCP = """In my FastMCP server, I tried to access the request context inside a tool function by instantiating Context(), but it raises `RuntimeError: No active MCP request context`. How do I correctly access the MCP Context inside a FastMCP tool?

from fastmcp import FastMCP, Context

mcp = FastMCP("demo")

@mcp.tool()
def process_data(data: str) -> str:
    ctx = Context()  # raises RuntimeError!
    ctx.info(f"Processing {data}")
    return data.upper()
"""

print("==================================================")
print("PROBE 1: Python 3.13 asyncio.Queue.shutdown()")
print("==================================================")
r1 = call_agent(PROBE_1_QUEUE)
print(r1)
print("\n" + "="*50 + "\n")

print("==================================================")
print("PROBE 2: Pydantic ConfigDict(defer_build=True)")
print("==================================================")
r2 = call_agent(PROBE_2_PYDANTIC_DEFER)
print(r2)
print("\n" + "="*50 + "\n")

print("==================================================")
print("PROBE 3: FastMCP Context Injection")
print("==================================================")
r3 = call_agent(PROBE_3_FASTMCP)
print(r3)
print("\n" + "="*50 + "\n")
