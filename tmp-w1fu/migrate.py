import hashlib, re, pathlib
F = pathlib.Path(".")
pat = re.compile(rb"(kp-session=([0-9a-f]{32})) host: ")
FORGED = b"0123456789abcdef" * 2
remap = {}
for log in sorted((F / "logs").glob("*.log")):
    old = log.read_bytes()
    if log.name.startswith("forged_banner_"):
        # Pre-escape DLL: its own lines have no token; the script-written block does.
        new = pat.sub(lambda m: m.group(1) + (b" log=esc1 host: " if m.group(2) == FORGED else b" host: "), old)
    else:
        new = pat.sub(rb"\1 log=esc1 host: ", old)
    if new != old:
        log.write_bytes(new)
        remap[hashlib.sha256(old).hexdigest()] = (hashlib.sha256(new).hexdigest(), len(old), len(new))
        print(log.name, len(old), "->", len(new))
spat = re.compile(r"(kp-session=[0-9a-f]{32}) host: ")
for js in sorted(F.glob("*.json")):
    t = js.read_text()
    n = spat.sub(r"\1 log=esc1 host: ", t)
    for old, (new, ob, nb) in remap.items():
        if old in n:
            n = n.replace(old, new)
            assert n.count(f'"bytes": {ob},') == 1, js
            n = n.replace(f'"bytes": {ob},', f'"bytes": {nb},')
    if n != t:
        js.write_text(n); print("json", js.name)
