# Case-insensitive scan: names defined/assigned/accessed as kp.X or bare-called
# in changed files vs NWScript routine names in data/routines/{k1,k2}.json.
import json, re, sys
root = sys.argv[1]
names = {}
for g in ('k1', 'k2'):
    d = json.load(open(f'{root}/data/routines/{g}.json'))
    def walk(x):
        if isinstance(x, dict):
            if 'name' in x and isinstance(x['name'], str): names[x['name'].lower()] = x['name']
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(d)
print('routine names:', len(names))
files = sys.argv[2:]
def strip(src):
    src = re.sub(r'--\[(=*)\[.*?\]\1\]', '', src, flags=re.S)
    src = re.sub(r'--[^\n]*', '', src)
    src = re.sub(r'"(?:\\.|[^"\\])*"', '""', src)
    src = re.sub(r"'(?:\\.|[^'\\])*'", "''", src)
    return src
for f in files:
    raw = open(f).read(); src = strip(raw)
    hits = set()
    for m in re.finditer(r'\bfunction\s+([A-Za-z_][\w.:]*)', src):
        hits.add(('funcdef', m.group(1).split('.')[-1].split(':')[-1]))
    for m in re.finditer(r'\blocal\s+function\s+([A-Za-z_]\w*)', src): hits.add(('localfunc', m.group(1)))
    for m in re.finditer(r'\blocal\s+([A-Za-z_][\w\s,]*)=', src):
        for n in m.group(1).split(','): hits.add(('local', n.strip()))
    for m in re.finditer(r'\bkp\.([A-Za-z_]\w*)', src): hits.add(('kp.field', m.group(1)))
    for m in re.finditer(r'(?<![.:\w])([A-Za-z_]\w*)\s*\(', src): hits.add(('barecall', m.group(1)))
    for m in re.finditer(r'(?m)^\s*([A-Za-z_]\w*)\s*=', src): hits.add(('globalassign', m.group(1)))
    for m in re.finditer(r'([A-Za-z_]\w*)\s*=\s*function', src): hits.add(('keyfunc', m.group(1)))
    bad = sorted((k, n, names[n.lower()]) for k, n in hits if n and n.lower() in names)
    print(f'== {f}: {len(bad)} collisions')
    for b in bad: print('  ', b)
