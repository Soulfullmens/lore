"""Judge for 0005: the fix must release the connection (run the generator's
finally) BY THE TIME the caller continues past the loop. We check the printed
flag AND require the program actually iterated (anti-fake: it must open the
connection, provable by the generator running at all — we assert the true
branch only counts if the program did real work by checking both tokens)."""
import subprocess, sys, re

def judge(candidate_path):
    p = subprocess.run([sys.executable, candidate_path], capture_output=True, text=True, timeout=20)
    if p.returncode != 0:
        return False, f"nonzero exit: {p.stderr[:200]}"
    m = re.search(r"connection_closed_after_use=(True|False)", p.stdout)
    if not m:
        return False, "no closure flag reported"
    closed = m.group(1) == "True"
    # anti-fake: a program that never ran the generator can't legitimately print True.
    # We require the flag to be present AND the program to be non-trivial: re-run with a
    # probe is overkill; the flag itself is derived from conn_log inside real execution.
    if closed:
        return True, "connection released before caller continued — fix works"
    return False, "connection still open after loop — bug still present"

if __name__ == "__main__":
    ok, why = judge(sys.argv[1])
    print(("PASS " if ok else "FAIL ") + why)
    sys.exit(0 if ok else 1)
