#!/bin/bash
# Installer re-review probes. Fake game folders only, under $P/games.
P=/home/brunner56/kp-live-20260922/review-probes-w1-r2; H=/home/brunner56/.local/bin/host-cmd
run(){ G="$1"; shift; $H pwsh -NoProfile -NonInteractive -File $P/Install-probe.ps1 -GameDir "$G" -SourceDir $P/src -AddressDir $P/addr "$@" 2>&1 | grep -v '^\s*$' | tail -3 | cut -c1-220; echo "rc=${PIPESTATUS[0]}"; }
edit(){ python3 - "$1" "$2" <<'PY'
import json,sys,hashlib
p=sys.argv[1]+"/kotorphasor/install-manifest.json"; m=json.load(open(p,encoding="utf-8-sig")); exec(sys.argv[2]); open(p,"w").write(json.dumps(m))
PY
}
fresh(){ G=$P/games/nest-$1/g; rm -rf $P/games/nest-$1; $P/mkgame.sh $G; echo keep > $P/games/nest-$1/sentinel.txt; run $G >/dev/null; }
check(){ G=$P/games/nest-$1/g; printf 'after: '; for f in swkotor.exe chitin.key binkw32.dll binkw32_real.dll kphasor.dll kotorphasor/install-manifest.json; do [ -e "$G/$f" ] && printf '%s ' "$f" || printf '!%s ' "$f"; done; [ -e $P/games/nest-$1/sentinel.txt ] && echo "| sentinel ok" || echo "| SENTINEL GONE"; [ -e $G/binkw32.dll ] && echo "  bink sha: $(sha256sum $G/binkw32.dll | cut -c1-12)"; }
t(){ name=$1; expr=$2; echo "=== $name :: $expr"; fresh $name; edit $P/games/nest-$name/g "$expr"; run $P/games/nest-$name/g -Action Uninstall; check $name; }
B='m["backup_dir"]'
echo "=== HAPPY path 'KotOR [GOG] Ünï 字'"
G="$P/games/KotOR [GOG] Ünï 字"; $P/mkgame.sh "$G"; run "$G"; run "$G" -Action Status; run "$G"; run "$G" -Action Uninstall; ls -A "$G"; sha256sum "$G/binkw32.dll" | cut -c1-12
t T1 "$B='.'"
t T9 "$B='..'"
t T2 "m['files'].insert(0,{'path':'../sentinel.txt','action':'created','sha256':hashlib.sha256(open('$P/games/nest-T2/sentinel.txt','rb').read()).hexdigest()})"
t T2b "m['files'].insert(0,{'path':'..\\\\sentinel.txt','action':'created','sha256':'0'*64})"
t N1null "$B=None"
t N1empty "$B=''"
t N1missing "del m['backup_dir']"
t N2dotdotTail "$B='kotorphasor/backup/20260101T000000Z/..'"
t N2abs "$B='$P/games/nest-N2abs'"
t N2unc "$B='\\\\\\\\?\\\\C:\\\\kotorphasor\\\\backup\\\\20260101T000000Z'"
t N2dev "$B='\\\\\\\\.\\\\C:'"
t N2trailnl "$B=m['backup_dir']+'\\n'"
t N2case "$B=m['backup_dir'].upper()"
t N3ads "m['files'][1]['path']='kphasor.dll:evil'"
t N3trdot "m['files'][1]['path']='kphasor.dll.'"
t N3trsp "m['files'][1]['path']='kphasor.dll '"
t N3short "m['files'][1]['path']='KPHASO~1.DLL'"
t N3drive "m['files'][1]['path']='C:kphasor.dll'"
t N3gamefile "m['files'][1]['path']='chitin.key'"
t N4arrBD "$B=[m['backup_dir']]"
t N4arrPath "m['files'][1]['path']=[m['files'][1]['path']]"
t N4arrSha "m['files'][1]['sha256']=[m['files'][1]['sha256']]"
t N4filesObj "m['files']=m['files'][1]"
t N4filesStr "m['files']='kphasor.dll'"
t N4filesEmpty "m['files']=[]"
t N4filesNull "m['files']=None"
t N4schema "m['schema']=['kotorphasor.install-manifest/v1']"
echo "--- manifest after N4filesObj (partial uninstall?):"; ls -A $P/games/nest-N4filesObj/g
t N9dup "m['files'].insert(1,dict(m['files'][1]))"
echo "--- N9dup rerun:"; run $P/games/nest-N9dup/g -Action Uninstall; check N9dup
echo DONE
