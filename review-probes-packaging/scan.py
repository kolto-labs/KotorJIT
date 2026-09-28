import zipfile, re, sys, collections, json, hashlib
z = zipfile.ZipFile(sys.argv[1])
names = z.namelist()
print('entries', len(names), 'testzip', z.testzip())
print('suffixes', collections.Counter(n.rsplit('.',1)[-1] if '.' in n.rsplit('/',1)[-1] else '(none)' for n in names))
MAGIC = {b'\x89PNG':'png', b'GIF8':'gif', b'\xff\xd8\xff':'jpg', b'RIFF':'riff/wav', b'BIKi':'bik', b'BIK':'bik', b'\x00\x00\x00':'mp4?',
         b'BIFFV1':'bif', b'KEY V1':'key', b'ERF ':'erf', b'MOD ':'mod', b'RIM ':'rim', b'TLK ':'tlk', b'2DA ':'2da', b'GFF ':'gff',
         b'SAV ':'sav', b'PK\x03\x04':'zip', b'\x7fELF':'elf', b'MZ':'pe', b'\x1aE\xdf\xa3':'mkv/webm', b'ID3':'mp3', b'OggS':'ogg'}
bad = []
for n in names:
    d = z.read(n)
    for m, k in MAGIC.items():
        if d.startswith(m): bad.append((n, k))
    if n.startswith('/') or '..' in n.split('/') or '\\' in n or not n.startswith('kotorphasor-creative-harness/'):
        bad.append((n, 'unsafe-name'))
    try: d.decode('utf-8')
    except UnicodeDecodeError: bad.append((n, 'non-utf8'))
print('magic/name/binary findings', bad)
pat = re.compile(rb'/home/|/run/media|/Users/|brunner56|bodencrouch|arrenkaetris|halomastar|\.superpowers|kp-live|kp-release|MyBook|\.worktrees|/tmp/|linuxbrew|C:\\\\Users|data/adjudication|data/research|next-k1-preparations|\d{8}-\d{6}-[0-9a-f]{8}', re.I)
hits = collections.defaultdict(list)
for n in names:
    for i, line in enumerate(z.read(n).splitlines(), 1):
        for m in pat.finditer(line):
            hits[n].append((i, m.group().decode(errors='replace'), line.strip()[:140].decode(errors='replace')))
for n, h in hits.items():
    print('==', n, len(h))
    for x in h[:12]: print('   ', x)
