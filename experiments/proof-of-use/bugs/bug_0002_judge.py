import subprocess, sys, re, pathlib
PROBE = str(pathlib.Path(__file__).with_name("bug_0002_probe.py"))
ORIG = str(pathlib.Path(__file__).with_name("bug_0002_buggy.py"))

def _settled(path):
    p = subprocess.run([sys.executable, PROBE, path], capture_output=True, text=True, timeout=20)
    if p.returncode == 2:
        # Candidate itself is broken (syntax/import/runtime). A real negative,
        # reported path-free from the probe's clean single line.
        m = re.search(r"PROBE candidate_error=(.*)", p.stderr)
        return None, "candidate_error " + (m.group(1).strip() if m else "unknown")
    if p.returncode != 0:
        # Unexpected exit: harness/probe malfunction, NOT a graded candidate failure.
        return None, "probe_error (harness)"
    m = re.search(r"PROBE settled=\[([^\]]*)\]", p.stdout)
    if not m:
        return None, "no settled reported"
    ids = [int(x) for x in m.group(1).split(",") if x.strip()]
    return set(ids), ""

def judge(candidate_path):
    orig, err = _settled(ORIG)
    if orig is None or orig == {1, 3}:   # original MUST lose siblings (bug real)
        return False, f"probe invalid: original already settles all ({orig}) {err}"
    cand, err = _settled(candidate_path)
    if cand is None:
        return False, f"candidate failed: {err}"
    if cand == {1, 3}:
        return True, f"all non-failing accounts settled {sorted(cand)} vs original {sorted(orig)} — fix works"
    return False, f"only {sorted(cand)} settled — sibling outcomes still lost"

if __name__ == "__main__":
    ok, why = judge(sys.argv[1]); print(("PASS " if ok else "FAIL ")+why); sys.exit(0 if ok else 1)
