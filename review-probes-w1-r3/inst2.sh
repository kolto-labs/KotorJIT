#!/bin/bash
P=/home/brunner56/kp-live-20260922/review-probes-w1-r3; H=/home/brunner56/.local/bin/host-cmd
source <(sed -n '/^run()/,/^B=/p' $P/inst.sh)
echo "=== T3 backup missing, binkw32_real.dll = original"
fresh T3; G=$P/games/nest-T3/g; rm -rf $G/kotorphasor/backup; run $G -Action Uninstall; check T3
echo "=== T4 backup tampered"
fresh T4; G=$P/games/nest-T4/g; for f in $G/kotorphasor/backup/*/binkw32.dll; do echo evil > "$f"; done; run $G -Action Uninstall; check T4
echo "=== T4b backup tampered AND binkw32_real tampered"
fresh T4b; G=$P/games/nest-T4b/g; for f in $G/kotorphasor/backup/*/binkw32.dll; do echo evil > "$f"; done; echo evil > $G/binkw32_real.dll; run $G -Action Uninstall; check T4b
echo "=== T5 read-only bink (chmod 444)"
G=$P/games/nest-T5/g; rm -rf $P/games/nest-T5; $P/mkgame.sh $G; echo keep > $P/games/nest-T5/sentinel.txt; chmod 444 $G/binkw32.dll; run $G; run $G -Action Uninstall; check T5
echo "=== T6 pre-existing addresses/k1_gog_103.json"
G=$P/games/nest-T6/g; rm -rf $P/games/nest-T6; $P/mkgame.sh $G; mkdir -p $G/kotorphasor/addresses; echo old > $G/kotorphasor/addresses/k1_gog_103.json; run $G; (cd $G && find . | sort | tr '\n' ' '); echo; cat $G/binkw32.dll | sha256sum | cut -c1-12
echo "=== T7 unknown bink, then -TrustBinkSha256 uppercase"
G=$P/games/nest-T7/g; rm -rf $P/games/nest-T7; $P/mkgame.sh $G; echo other-bink > $G/binkw32.dll; S=$(sha256sum $G/binkw32.dll|cut -c1-64|tr a-f A-F); run $G; run $G -TrustBinkSha256 $S; grep -o '"bink_trusted_override": *"[0-9a-f]*"' $G/kotorphasor/install-manifest.json
echo "=== T8 relative GameDir"
G=$P/games/nest-T8/g; rm -rf $P/games/nest-T8; $P/mkgame.sh $G; cd $P/games/nest-T8; run g; run g -Action Uninstall; cd /
echo "=== S1 symlinked backup timestamp dir -> outside victim dir"
fresh S1; G=$P/games/nest-S1/g; mkdir -p $P/games/nest-S1/victimdir; echo precious > $P/games/nest-S1/victimdir/precious.txt
TS=$(ls $G/kotorphasor/backup); mv $G/kotorphasor/backup/$TS $P/games/nest-S1/realbackup; cp $P/games/nest-S1/realbackup/binkw32.dll $P/games/nest-S1/victimdir/; ln -s $P/games/nest-S1/victimdir $G/kotorphasor/backup/$TS
run $G -Action Uninstall; check S1; echo "victimdir:"; ls -A $P/games/nest-S1/victimdir 2>&1; ls -la $G/kotorphasor/backup 2>&1 | tail -2
echo "=== S2 kotorphasor dir itself a symlink to outside"
fresh S2; G=$P/games/nest-S2/g; mv $G/kotorphasor $P/games/nest-S2/kpreal; ln -s $P/games/nest-S2/kpreal $G/kotorphasor; echo precious > $P/games/nest-S2/kpreal/scripts/mine.lua
run $G -Action Uninstall; check S2; ls -A $P/games/nest-S2/kpreal $P/games/nest-S2/kpreal/scripts
t N5actArr "f=m['files'][1]; f['action']=['created','replaced']; f['original_sha256']=hashlib.sha256(open('$P/games/nest-N5actArr/g/chitin.key','rb').read()).hexdigest(); f['backup']='chitin.key'"
echo "  kphasor.dll content now:"; head -c 40 $P/games/nest-N5actArr/g/kphasor.dll 2>&1; echo
t N10order "r=[f for f in m['files'] if f['path']=='binkw32_real.dll'][0]; m['files'].remove(r); m['files'].append(r); import shutil; shutil.rmtree('$P/games/nest-N10order/g/kotorphasor/backup')"
t N11onlyKp "m['files']=[f for f in m['files'] if f['path']=='kphasor.dll']"
echo "=== H1 huge manifest: 20000 created entries (missing files)"
fresh H1; G=$P/games/nest-H1/g; edit $G "m['files']=[{'path':'kotorphasor/addresses/x%d.json'%i,'action':'created','sha256':'0'*64} for i in range(20000)]+m['files']"
ls -la $G/kotorphasor/install-manifest.json | awk '{print $5" bytes"}'; /usr/bin/time -f '%e s' bash -c "$(declare -f run); P=$P; H=$H; run $G -Action Uninstall"; check H1
echo "=== H2 deep nesting JSON"
fresh H2; G=$P/games/nest-H2/g; python3 -c "
p='$G/kotorphasor/install-manifest.json'; import json; m=json.load(open(p,encoding='utf-8-sig')); d={}; x=d
for i in range(3000): x['a']={}; x=x['a']
m['junk']=d; open(p,'w').write(json.dumps(m))" 2>&1 | tail -1; run $G -Action Uninstall; check H2
echo DONE
