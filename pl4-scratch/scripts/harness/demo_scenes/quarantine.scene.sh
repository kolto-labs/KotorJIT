say "A script that errors every tick gets quarantined after three strikes."
beat 1
run "./build/kp_luatest scripts/examples/edge_quarantine OnTick 1 --repeat 5"
beat 2
say "Dispatch stops — the host does not hang on the same stack trace forever."
