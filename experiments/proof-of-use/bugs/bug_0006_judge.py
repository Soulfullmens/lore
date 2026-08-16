"""Judge 0006. No leak: the agent-facing buggy file has no measurement print.
The probe (unseen by agent) imports run_batch() and measures ping latency under
load. A candidate PASSES iff: (a) probe on candidate shows responsive ping, AND
(b) probe on the ORIGINAL buggy file shows starvation — proving the bug was real
and the probe discriminates. Anti-fake wall-clock ensures the batch actually ran."""
import subprocess, sys, re, time, pathlib

PROBE = str(pathlib.Path(__file__).with_name("bug_0006_probe.py"))
ORIG_BUGGY = str(pathlib.Path(__file__).with_name("bug_0006_buggy.py"))
THRESHOLD = 0.3

def _probe(path):
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, PROBE, path], capture_output=True, text=True, timeout=30)
    wall = time.monotonic() - t0
    if p.returncode == 2:
        m = re.search(r"PROBE candidate_error=(.*)", p.stderr)
        return None, wall, "candidate_error " + (m.group(1).strip() if m else "unknown")
    if p.returncode != 0:
        return None, wall, "probe_error (harness)"
    m = re.search(r"PROBE ping_latency=([\d.]+)", p.stdout)
    return (float(m.group(1)) if m else None), wall, ""

def judge(candidate_path):
    # (b) confirm the bug is real on the untouched buggy file
    orig_lat, _, err = _probe(ORIG_BUGGY)
    if orig_lat is None or orig_lat < THRESHOLD:
        return False, f"probe invalid: original buggy file not starved ({orig_lat}) {err}"
    # (a) grade the candidate
    lat, wall, err = _probe(candidate_path)
    if lat is None:
        return False, f"candidate failed: {err}"
    if wall < 0.4:
        return False, f"ran too fast ({wall:.2f}s) — batch not actually executed"
    if lat < THRESHOLD:
        return True, f"ping responsive ({lat:.3f}s) vs original starved ({orig_lat:.3f}s) — fix works"
    return False, f"ping still starved ({lat:.3f}s) — bug present"

if __name__ == "__main__":
    ok, why = judge(sys.argv[1])
    print(("PASS " if ok else "FAIL ") + why)
    sys.exit(0 if ok else 1)
