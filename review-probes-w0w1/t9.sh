H=/home/brunner56/.local/bin/host-cmd
$H pwsh -NoProfile -NonInteractive -File /home/brunner56/kp-live-20260922/review-probes-w0w1/lastmatch.ps1 2>&1
$H pwsh -NoProfile -NonInteractive -File /home/brunner56/kp-live-20260922/review-probes-w0w1/Install-probe.ps1 -GameDir /home/brunner56/kp-live-20260922/review-probes-w0w1/games/nest/t9 -SourceDir /home/brunner56/kp-live-20260922/review-probes-w0w1/src -AddressDir /home/brunner56/kp-live-20260922/review-probes-w0w1/addr 2>&1 | tail -1
python3 -c "
import json;p='/home/brunner56/kp-live-20260922/review-probes-w0w1/games/nest/t9/kotorphasor/install-manifest.json';m=json.load(open(p,encoding='utf-8-sig'));m['backup_dir']='..';open(p,'w').write(json.dumps(m))"
$H pwsh -NoProfile -NonInteractive -File /home/brunner56/kp-live-20260922/review-probes-w0w1/Install-probe.ps1 -GameDir /home/brunner56/kp-live-20260922/review-probes-w0w1/games/nest/t9 -Action Uninstall 2>&1 | grep -v '^\s*$' | tail -3
echo "games/ after:"; ls -A /home/brunner56/kp-live-20260922/review-probes-w0w1/games; echo "nest exists?"; ls -A /home/brunner56/kp-live-20260922/review-probes-w0w1/games/nest 2>&1
