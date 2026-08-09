"""Judge for bug 0006: run the candidate script; the fix is correct iff the
health ping stayed responsive (latency well under the starvation threshold)
WHILE 8 blocking jobs ran. We parse the latency the script prints. To prevent
gaming by simply printing a fake number, we also require the script actually
ran the batch (wall-clock >= the job duration) — a print-only fake finishes
too fast and is rejected."""
import subprocess, sys, re, time

def judge(candidate_path):
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, candidate_path], capture_output=True, text=True, timeout=30)
    wall = time.monotonic() - t0
    if p.returncode != 0:
        return False, f"nonzero exit: {p.stderr[:200]}"
    m = re.search(r"latency:\s*([\d.]+)s", p.stdout)
    if not m:
        return False, "no latency reported"
    latency = float(m.group(1))
    # anti-fake: the real scenario must actually run the ~0.5s blocking batch
    if wall < 0.4:
        return False, f"ran too fast ({wall:.2f}s) — batch not actually executed"
    # correctness: ping must stay responsive (fix isolates it from the job pool)
    if latency < 0.3:
        return True, f"ping responsive ({latency:.3f}s) under load — fix works"
    return False, f"ping starved ({latency:.3f}s) — bug still present"

if __name__ == "__main__":
    ok, why = judge(sys.argv[1])
    print(("PASS " if ok else "FAIL ") + why)
    sys.exit(0 if ok else 1)
