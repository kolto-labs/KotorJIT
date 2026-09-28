cd /run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
echo "cursed.lua $(sha256sum tools/tests/examples/cursed.lua | cut -c1-12) chain $(sha256sum scripts/examples/cursed/40_chain_reaction.lua | cut -c1-12)"
echo '=== current'; /usr/bin/luajit /home/brunner56/kp-live-20260922/review-probes-examples-r5/runner.lua /home/brunner56/kp-live-20260922/review-probes-examples-r5/current.map.lua | grep -v '^PASS'
for m in mut-no-firstpc mut-no-party mut-no-load-clear mut-truthy-save mut-fail-open mut-false-as-unknown mut-cache-spared mut-cache-party; do echo "=== $m"; /usr/bin/luajit /home/brunner56/kp-live-20260922/review-probes-examples-r5/runner.lua /home/brunner56/kp-live-20260922/review-probes-examples-r5/$m.map.lua | grep -v '^PASS'; done
