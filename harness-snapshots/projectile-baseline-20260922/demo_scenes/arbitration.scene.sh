say "Six scripts disagree about one OnRunScript event."
say "kp_luatest dispatches it once and prints who claimed it."
beat 1
run "./build/kp_luatest scripts/examples/arbitration OnRunScript k_def_heartbt01 0 0"
beat 2
say "Priority 80's string \"1\" wins — after two higher scripts abstain."
