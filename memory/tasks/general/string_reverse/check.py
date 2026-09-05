"""Deterministic grader for reverse_words."""
import sys

from solution import reverse_words

cases = [
    ("hello world", "world hello"),
    ("the quick brown fox", "fox brown quick the"),
    ("single", "single"),
    ("", ""),
    ("a b c", "c b a"),
]

failed = 0
for inp, expected in cases:
    got = reverse_words(inp)
    if got != expected:
        print(f"FAIL: reverse_words({inp!r}) = {got!r}, expected {expected!r}", file=sys.stderr)
        failed += 1

if failed:
    sys.exit(1)
print("OK")
