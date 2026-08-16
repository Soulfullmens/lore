import asyncio, sys, importlib.util

def load(path):
    spec = importlib.util.spec_from_file_location("candidate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def _fail(reason):
    print(f"PROBE candidate_error={reason}", file=sys.stderr)
    sys.exit(2)

try:
    mod = load(sys.argv[1])
    latency = asyncio.run(mod.run_batch())
except SyntaxError as e:
    _fail(f"SyntaxError: {e.msg}")
except Exception as e:
    _fail(f"{type(e).__name__}: {e}")

try:
    latency = float(latency)
except (TypeError, ValueError):
    _fail(f"BadReturn: run_batch() returned {type(latency).__name__}, expected float")

# probe decides pass/fail by BEHAVIOR, not by anything the candidate printed
print(f"PROBE ping_latency={latency:.3f}")
