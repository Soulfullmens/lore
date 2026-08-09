import asyncio, sys, importlib.util
def load(p):
    s = importlib.util.spec_from_file_location("candidate", p); m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m); return m
mod = load(sys.argv[1])
async def main():
    matched, snapshot = await mod.find_first("alice")
    # BEHAVIOR at the moment find_first returned (inside the loop, pre-teardown)
    print(f"PROBE closed_on_return={'close' in snapshot}")
asyncio.run(main())
