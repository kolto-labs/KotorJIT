#!/bin/bash
P=/home/brunner56/kp-live-20260922/review-probes-w0w1; H=/home/brunner56/.local/bin/host-cmd
run(){ G="$1"; shift; $H pwsh -NoProfile -NonInteractive -File $P/Install-probe.ps1 -GameDir "$G" -SourceDir $P/src -AddressDir $P/addr "$@" 2>&1 | grep -v '^\s*$' | tail -4; echo "rc=${PIPESTATUS[0]}"; }
edit(){ python3 - "$1" "$2" <<'PY'
import json,sys
p=sys.argv[1]+"/kotorphasor/install-manifest.json"; m=json.load(open(p,encoding="utf-8-sig")); exec(sys.argv[2]); open(p,"w").write(json.dumps(m))
PY
}
echo "=== T1 backup_dir='.' (tampered manifest)"
G=$P/games/t1; $P/mkgame.sh $G; run $G >/dev/null; edit $G 'm["backup_dir"]="."'
run $G -Action Uninstall; echo "after:"; ls -A $G 2>&1
echo "=== T2 created path traversal ../victim.txt with its hash"
G=$P/games/t2; $P/mkgame.sh $G; echo victim > $P/games/victim.txt; run $G >/dev/null
edit $G 'import hashlib; m["files"].insert(0,{"path":"../victim.txt","action":"created","sha256":hashlib.sha256(open("'$P'/games/victim.txt","rb").read()).hexdigest()})'
run $G -Action Uninstall; ls $P/games/victim.txt 2>&1
echo "=== T3 backup missing, binkw32_real.dll (=original) present"
G=$P/games/t3; $P/mkgame.sh $G; run $G >/dev/null; rm -rf $G/kotorphasor/backup
run $G -Action Uninstall; sha256sum $G/binkw32.dll $G/binkw32_real.dll | cut -c1-16
echo "=== T4 backup tampered"
G=$P/games/t4; $P/mkgame.sh $G; run $G >/dev/null; echo evil > $G/kotorphasor/backup/*/binkw32.dll
run $G -Action Uninstall; ls -A $G
echo "=== T5 read-only original binkw32.dll (Linux chmod 444 on file)"
G=$P/games/t5; $P/mkgame.sh $G; chmod 444 $G/binkw32.dll; run $G; ls -l $G/binkw32.dll $G/binkw32_real.dll; run $G -Action Uninstall; ls -A $G; ls -l $G/binkw32.dll
echo "=== T6 existing kotorphasor/addresses/k1_gog_103.json from manual install"
G=$P/games/t6; $P/mkgame.sh $G; mkdir -p $G/kotorphasor/addresses; echo old > $G/kotorphasor/addresses/k1_gog_103.json; run $G; find $G | sort
echo "=== T7 TrustBinkSha256 on unknown bink, uppercase"
G=$P/games/t7; $P/mkgame.sh $G; echo other-bink > $G/binkw32.dll; S=$(sha256sum $G/binkw32.dll|cut -c1-64|tr a-f A-F); run $G; run $G -TrustBinkSha256 $S; grep -A0 trusted $G/kotorphasor/install-manifest.json
echo "=== T8 relative GameDir from other cwd"
G=$P/games/t8; $P/mkgame.sh $G; cd $P/games; run t8; cd /
echo DONE
