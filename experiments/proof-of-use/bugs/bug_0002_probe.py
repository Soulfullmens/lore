import asyncio, sys, importlib.util

def load(p):
    s = importlib.util.spec_from_file_location("candidate", p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m

def _fail(reason):
    # One clean line, no traceback. Raw tracebacks leak absolute filesystem paths
    # (incl. the username) into committed results. Exit 2 == candidate is broken,
    # which is a REAL negative result, distinct from a harness/probe malfunction.
    print(f"PROBE candidate_error={reason}", file=sys.stderr)
    sys.exit(2)

try:
    mod = load(sys.argv[1])
    outcomes = asyncio.run(mod.charge_all())
except SyntaxError as e:
    _fail(f"SyntaxError: {e.msg}")            # e.msg omits the file path
except Exception as e:
    _fail(f"{type(e).__name__}: {e}")

if not hasattr(outcomes, "keys"):
    _fail(f"BadReturn: charge_all() returned {type(outcomes).__name__}, expected dict")

# BEHAVIOR: both non-failing accounts (1 and 3) must be settled at return
print(f"PROBE settled={sorted(outcomes.keys())}")
