-- Round-4 adversarial probes for 40_chain_reaction.lua (host fixture only).
-- Run from the worktree root: luajit r4_probes.lua [alt_source]
local F = assert(loadfile("tools/tests/examples/fixture.lua"))()
local path = "scripts/examples/cursed/40_chain_reaction.lua"
F.sources = { [path] = arg and arg[1] or path }
local function fresh(ov) return F.new(path, ov):load() end
local function sets(f, from)
  local out = {}
  for i = (from or 0) + 1, #f.calls do local c = f.calls[i]
    if c.name == "SetMinOneHP" then out[#out+1] = ("%s<-%s"):format(tostring(c.args[1]), tostring(c.args[2])) end end
  return table.concat(out, " ")
end
local function nprint(f, text) local n = 0 for _, s in ipairs(f.prints) do if s:find(text, 1, true) then n = n + 1 end end return n end
local function lines(f, text) local o = {} for _, s in ipairs(f.prints) do if s:find(text, 1, true) then o[#o+1] = s end end return table.concat(o, " || ") end

-- R4-1a: PC tag unknown (GetTag errors for the PC). Guard, then module load
-- with PC under a new ID; GetTag still errors for the PC.
do
  local f = fresh(); f.area_objects = {20, 21, 1}
  local real = function(id) return (f.objects[id] or {}).tag or '' end
  f.overrides.GetTag = function(id) if id == 1 or id == 7 then error("bridge refused") end return real(id) end
  f:arm(); f.env.OnRunScript("k_def_death01", 20)
  local during = f.objects[1].min_one_hp
  f.objects[7] = {tag = "pc", party = 1, x = 0, min_one_hp = 1}; f.objects[1] = nil; f.party = {7, 2}
  f.overrides.GetFirstPC = function() return 7 end
  local before = #f.calls
  f.env.OnModuleLoad()
  print(("R4-1a PC tag errors: during=%s new_pc(7)=%s sets=[%s] pending=%d")
    :format(tostring(during), tostring(f.objects[7].min_one_hp), sets(f, before), nprint(f, "restore pending")))
end
-- R4-1b: PC tag "" and the player switches control to bastila inside the
-- module; then an OnAreaEnter (same module) bumps the epoch; settle runs.
do
  local f = fresh(); f.objects[1].tag = ""; f.area_objects = {20, 21, 1}
  f:arm(); f.env.OnRunScript("k_def_death01", 20)
  f.overrides.GetFirstPC = function() return 2 end        -- control swap, PC 1 still valid
  f.env.OnAreaEnter(99, 23)                                -- some creature enters, same module
  local after_enter = f.objects[1].min_one_hp
  f:fire(#f.timers)
  local after_settle = f.objects[1].min_one_hp
  f.env.OnScriptUnload()
  print(("R4-1b PC tag '' + control swap + same-module OnAreaEnter: after_enter=%s after_settle=%s after_unload=%s pending=%d unload_line=%q")
    :format(tostring(after_enter), tostring(after_settle), tostring(f.objects[1].min_one_hp),
            nprint(f, "restore pending"), lines(f, "NOT restored")))
end
-- R4-1c: same as 1b but WITHOUT the OnAreaEnter (same epoch): control
-- baseline, shows what the bump costs.
do
  local f = fresh(); f.objects[1].tag = ""; f.area_objects = {20, 21, 1}
  f:arm(); f.env.OnRunScript("k_def_death01", 20)
  f.overrides.GetFirstPC = function() return 2 end
  f:fire(#f.timers)
  print(("R4-1c same, no OnAreaEnter: after_settle=%s pending=%d")
    :format(tostring(f.objects[1].min_one_hp), nprint(f, "restore pending")))
end

-- R4-2: two party members share a tag ('twin'), priors 0 and 0. Both are
-- guarded; then a same-module OnAreaEnter (IDs unchanged).
do
  local f = fresh()
  f.objects[3] = {tag = "twin", party = 1, x = 1, min_one_hp = 0}
  f.objects[4] = {tag = "twin", party = 1, x = 2, min_one_hp = 0}
  f.party = {1, 3, 4}; f.area_objects = {20, 21, 3, 4}
  f:arm(); f.env.OnRunScript("k_def_death01", 20)
  local d3, d4 = f.objects[3].min_one_hp, f.objects[4].min_one_hp
  local before = #f.calls
  f.env.OnAreaEnter(99, 23)
  f:fire(#f.timers); f.env.OnScriptUnload()
  print(("R4-2 two same-tag members + OnAreaEnter: during=%s,%s after=%s,%s sets=[%s] prior_unknown=%d pending=%d not_restored=%d")
    :format(tostring(d3), tostring(d4), tostring(f.objects[3].min_one_hp), tostring(f.objects[4].min_one_hp),
            sets(f, before), nprint(f, "prior unknown"), nprint(f, "restore pending"), nprint(f, "NOT restored")))
  -- Follow-up: the stuck twin is blasted again; is its stuck 1 read as a prior?
  f:arm(); f.objects[22] = {tag = "sith3", x = 2}; f.area_objects = {22, 4}
  f.env.OnRunScript("k_def_death01", 22); f:fire(#f.timers)
  print(("R4-2b stuck twin blasted again then settled: twin4=%s"):format(tostring(f.objects[4].min_one_hp)))
end

-- R4-3: party change inside the 3 s window: bastila leaves the party (still
-- valid, now non-party) before settle. Then she rejoins later.
do
  local f = fresh(); f:arm(); f.env.OnRunScript("k_def_death01", 20)
  f.objects[2].party = nil; f.party = {1}
  f:fire(#f.timers)
  local after_settle = f.objects[2].min_one_hp
  local pend = nprint(f, "restore pending")
  f.env.OnAreaEnter(99, 1)
  f.objects[2].party = 1; f.party = {1, 2}
  f.env.OnAreaEnter(99, 2)
  print(("R4-3 member leaves party in window: after_settle=%s pending=%d after_rejoin=%s")
    :format(tostring(after_settle), pend, tostring(f.objects[2].min_one_hp)))
end
-- R4-3b: same, but she never rejoins and the script unloads.
do
  local f = fresh(); f:arm(); f.env.OnRunScript("k_def_death01", 20)
  f.objects[2].party = nil; f.party = {1}
  f:fire(#f.timers); f.env.OnScriptUnload()
  print(("R4-3b left party, unload: bastila=%s unload_line=%q")
    :format(tostring(f.objects[2].min_one_hp), lines(f, "NOT restored")))
end

-- R4-4: blast, then module load while the roster is empty and GetFirstPC is
-- invalid (mid-transition); pending settle timer fires after the new module
-- is up (members under new IDs).
do
  local f = fresh(); f.area_objects = {20, 21, 2, 1}
  f:arm(); f.env.OnRunScript("k_def_death01", 20)
  local timer = #f.timers
  local saved = {f.objects[1], f.objects[2]}
  f.objects[1] = nil; f.objects[2] = nil; f.party = {}
  f.overrides.GetFirstPC = function() return F.INVALID end
  f.env.OnModuleLoad()
  local pend = nprint(f, "restore pending")
  -- new module up
  f.objects[11] = {tag = "pc", party = 1, x = 0, min_one_hp = saved[1].min_one_hp}
  f.objects[12] = {tag = "bastila", party = 1, x = 1, min_one_hp = saved[2].min_one_hp}
  f.party = {11, 12}; f.overrides.GetFirstPC = function() return 11 end
  local late = f:fire(timer)
  print(("R4-4 transition with empty roster; old settle timer fires after: pending_at_load=%d pc(11)=%s bastila(12)=%s")
    :format(pend, tostring(f.objects[11].min_one_hp), tostring(f.objects[12].min_one_hp)))
end
-- R4-4b: blast arrives during the transition (OnRunScript between
-- OnModuleLoad and arming): must not detonate.
do
  local f = fresh(); f:arm(); f.env.OnModuleLoad()
  local before = f:count("EffectDamage")
  f.env.OnRunScript("k_def_death01", 20)
  print(("R4-4b death during load window: EffectDamage delta=%d"):format(f:count("EffectDamage") - before))
end

-- R4-5: unload immediately after load (roster not yet up, new IDs).
do
  local f = fresh(); f.objects[1].tag = ""; f.area_objects = {20, 21, 2, 1}
  f:arm(); f.env.OnRunScript("k_def_death01", 20)
  f.objects[1] = nil; f.objects[2] = nil; f.party = {}
  f.overrides.GetFirstPC = function() return F.INVALID end
  f.env.OnModuleLoad(); f.env.OnScriptUnload()
  print(("R4-5 unload right after load: not_restored=%d lines=%q")
    :format(nprint(f, "NOT restored"), lines(f, "NOT restored")))
end

-- R4-6: OnAreaEnter storm inside one module (spawned creature enters each
-- time) while guarded; tagged members; count re-resolution cost and outcome.
do
  local f = fresh(); f.area_objects = {20, 21, 2, 1}
  f:arm(); f.env.OnRunScript("k_def_death01", 20)
  for i = 1, 5 do f.env.OnAreaEnter(99, 30 + i) end
  print(("R4-6 5x same-module OnAreaEnter, tagged: pc=%s bastila=%s guards_left_pending=%d armed_local5=%s")
    :format(tostring(f.objects[1].min_one_hp), tostring(f.objects[2].min_one_hp),
            nprint(f, "restore pending"), tostring(f.locals[5])))
end
-- R4-6b: untagged non-PC member, same-module OnAreaEnter (IDs unchanged).
do
  local f = fresh(); f.objects[3] = {tag = "", party = 1, x = 2, min_one_hp = 0}; f.party = {1, 2, 3}
  f.area_objects = {20, 21, 3}; f:arm(); f.env.OnRunScript("k_def_death01", 20)
  f.env.OnAreaEnter(99, 31)
  local after_enter = f.objects[3].min_one_hp
  f:fire(#f.timers)
  local after_settle = f.objects[3].min_one_hp
  f.env.OnScriptUnload()
  print(("R4-6b untagged member, same-module OnAreaEnter: after_enter=%s after_settle=%s after_unload=%s unload_line=%q")
    :format(tostring(after_enter), tostring(after_settle), tostring(f.objects[3].min_one_hp), lines(f, "NOT restored")))
end
-- R4-6c: OnAreaEnter mid-window with tagged members restores early: is the
-- member still protected against a blast that lands after re-arm but before
-- the old settle timer? (Timer from before the enter should not undo the new guard.)
do
  local f = fresh(); f.area_objects = {20, 21, 2}
  f:arm(); f.env.OnRunScript("k_def_death01", 20)
  local t1 = #f.timers
  f.env.OnAreaEnter(99, 31); f:arm()
  f.objects[22] = {tag = "sith3", x = 2}; f.area_objects = {22, 2}
  f.env.OnRunScript("k_def_death01", 22)
  f:fire(t1)
  local mid = f.objects[2].min_one_hp
  f:fire(#f.timers)
  print(("R4-6c stale timer after re-arm: bastila after old timer=%s after new=%s"):format(tostring(mid), tostring(f.objects[2].min_one_hp)))
end

-- R4-7: exploded[] keyed by raw ID across epochs: a new creature in the next
-- module under a recycled ID never detonates.
do
  local f = fresh(); f:arm(); f.env.OnRunScript("k_def_death01", 20)
  local c1 = f.locals[7]
  f.objects[20] = {tag = "new_module_sith", x = 3}
  f:arm(); f.env.OnRunScript("k_def_death01", 20)
  print(("R4-7 recycled ID corpse after load: detonations before=%s after=%s"):format(tostring(c1), tostring(f.locals[7])))
end

-- R4-8: guard carry onto a genuine untagged creature: PC tag '' unresolved
-- (control swapped after load); another untagged party member with a genuine
-- story prior 1 is blasted.
do
  local f = fresh(); f.objects[1].tag = ""; f.area_objects = {20, 21, 1}
  f:arm(); f.env.OnRunScript("k_def_death01", 20)            -- PC prior 0
  f.objects[5] = {tag = "", party = 1, x = 2, min_one_hp = 1} -- genuine 1
  f.party = {1, 2, 5}; f.overrides.GetFirstPC = function() return 5 end
  f.env.OnModuleLoad(); f:arm()
  f.objects[22] = {tag = "sith3", x = 2}; f.area_objects = {22, 5}
  f.env.OnRunScript("k_def_death01", 22); f:fire(#f.timers)
  f.overrides.GetFirstPC = function() return 1 end; f.env.OnAreaEnter(99, 1)
  print(("R4-8 untagged carry onto a genuine-1 member: member5=%s pc1=%s pending=%d")
    :format(tostring(f.objects[5].min_one_hp), tostring(f.objects[1].min_one_hp), nprint(f, "restore pending")))
end
