import asyncio, sys, importlib.util
def load(p):
    s = importlib.util.spec_from_file_location("candidate", p); m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m); return m
mod = load(sys.argv[1])
outcomes = asyncio.run(mod.charge_all())
# BEHAVIOR: both non-failing accounts (1 and 3) must be settled at return
print(f"PROBE settled={sorted(outcomes.keys())}")
