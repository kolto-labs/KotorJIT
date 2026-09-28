cd /run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation
P=/home/brunner56/kp-live-20260922
MAP=/home/brunner56/kp-live-20260922/review-probes-examples-r5/current.map.lua
S=scripts/examples/cursed/40_chain_reaction.lua
echo "=== chain sha $(sha256sum $S | cut -c1-12)"
export KP_TOLERANT=${KP_TOLERANT:-0}
for f in $P/review-probes-examples/chain_attacks.lua $P/review-probes-examples/pc_probe.lua $P/review-probes-examples/mutations.lua; do echo "##### $f"; /usr/bin/luajit $P/review-probes-examples-r5/run_blocks.lua $f $MAP 2>&1; done
for f in $P/review-probes-examples-r2/pc_swap_probe.lua $P/review-probes-examples-r3/r3_probes.lua $P/review-probes-examples-r4/r4_probes.lua $P/review-probes-examples-r4/r4_probes2.lua $P/review-probes-examples-r4/r4_probes3.lua $P/review-probes-examples-r4/r4_probe8_detail.lua; do echo "##### $f"; /usr/bin/luajit $P/review-probes-examples-r5/run_blocks.lua $f $S 2>&1; done
