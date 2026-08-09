import subprocess, sys, re, pathlib
PROBE = str(pathlib.Path(__file__).with_name("bug_0005_probe.py"))
ORIG = str(pathlib.Path(__file__).with_name("bug_0005_buggy.py"))
def _probe(path):
    p = subprocess.run([sys.executable, PROBE, path], capture_output=True, text=True, timeout=20)
    if p.returncode != 0: return None, p.stderr[:200]
    m = re.search(r"PROBE closed_on_return=(True|False)", p.stdout)
    return (m.group(1) == "True") if m else None, ""
def judge(candidate_path):
    orig, err = _probe(ORIG)
    if orig is not False:  # original MUST show the bug (not closed)
        return False, f"probe invalid: original not exhibiting bug (closed={orig}) {err}"
    cand, err = _probe(candidate_path)
    if cand is None: return False, f"candidate probe failed: {err}"
    if cand: return True, "connection closed on return vs original left open — fix works"
    return False, "connection still open on return — bug present"
if __name__ == "__main__":
    ok, why = judge(sys.argv[1]); print(("PASS " if ok else "FAIL ")+why); sys.exit(0 if ok else 1)
