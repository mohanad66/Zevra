"""Verify the EN and AR dictionaries stay in key parity."""
import re
import sys

PAT = re.compile(r"^\s*'([^']+)'\s*:", re.M)


def keys(path):
    with open(path, encoding="utf-8") as fh:
        return set(PAT.findall(fh.read()))


en = keys("src/i18n/en.js")
ar = keys("src/i18n/ar.js")
print("en keys: %d | ar keys: %d" % (len(en), len(ar)))
print("missing in ar:", sorted(en - ar) or "none")
print("missing in en:", sorted(ar - en) or "none")
new = ["admin.users.count", "admin.users.countFiltered"]
print("new keys in both:", all(k in en and k in ar for k in new))
sys.exit(0 if en == ar and all(k in en and k in ar for k in new) else 1)
