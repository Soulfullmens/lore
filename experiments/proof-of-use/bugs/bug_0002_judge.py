"""Judge for 0002: the fix must surface the outcome of ALL sibling operations,
not just the first exception. Correct approaches: return_exceptions=True, or a
TaskGroup that collects all results. We check the program reports that every
non-failing account settled AND reconciliation completed."""
import subprocess, sys, re

def judge(candidate_path):
    p = subprocess.run([sys.executable, candidate_path], capture_output=True, text=True, timeout=20)
    if p.returncode != 0:
        return False, f"nonzero exit: {p.stderr[:200]}"
    m = re.search(r"reconciliation_complete=(True|False)", p.stdout)
    if not m:
        return False, "no reconciliation flag reported"
    if m.group(1) == "True":
        return True, "all sibling outcomes captured — fix works"
    return False, "sibling outcomes lost after first failure — bug still present"

if __name__ == "__main__":
    ok, why = judge(sys.argv[1])
    print(("PASS " if ok else "FAIL ") + why)
    sys.exit(0 if ok else 1)
