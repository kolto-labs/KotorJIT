cd /run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
for src in scripts/examples/cursed/40_chain_reaction.lua /home/brunner56/kp-live-20260922/review-probes-examples-r4/chain_r3_74c0ca1a.lua /home/brunner56/kp-live-20260922/review-probes-examples-r4/chain_HEAD.lua /home/brunner56/kp-live-20260922/review-probes-examples-r4/mut-nobump-areaenter.lua; do
  echo "=== $src $(sha256sum $src | cut -c1-12)"
  /usr/bin/luajit /home/brunner56/kp-live-20260922/review-probes-examples-r4/r4_probes.lua $src 2>&1
  /usr/bin/luajit /home/brunner56/kp-live-20260922/review-probes-examples-r4/r4_probe8_detail.lua $src 2>&1
  /usr/bin/luajit /home/brunner56/kp-live-20260922/review-probes-examples-r4/r4_probes2.lua $src 2>&1
done
echo "=== writer's 22 tests on mut-nobump-areaenter"
/usr/bin/luajit /home/brunner56/kp-live-20260922/review-probes-examples-r4/runner.lua /home/brunner56/kp-live-20260922/review-probes-examples-r4/mut-nobump.map.lua 2>&1
echo "=== writer's 22 tests on current"
/usr/bin/luajit /home/brunner56/kp-live-20260922/review-probes-examples-r4/runner.lua /home/brunner56/kp-live-20260922/review-probes-examples-r4/current.map.lua 2>&1
