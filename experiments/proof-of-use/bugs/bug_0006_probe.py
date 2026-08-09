import asyncio, sys, importlib.util

def load(path):
    spec = importlib.util.spec_from_file_location("candidate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

mod = load(sys.argv[1])
latency = asyncio.run(mod.run_batch())
# probe decides pass/fail by BEHAVIOR, not by anything the candidate printed
print(f"PROBE ping_latency={latency:.3f}")
