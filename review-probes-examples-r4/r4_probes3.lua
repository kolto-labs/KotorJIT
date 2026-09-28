-- R4-1L: R4-1b with OnModuleLoad (IDs unchanged) instead of OnAreaEnter; and R4-2L: same-tag pair across a load.
local F = assert(loadfile("tools/tests/examples/fixture.lua"))()
local path = "scripts/examples/cursed/40_chain_reaction.lua"
F.sources = { [path] = arg and arg[1] or path }
local function nprint(f, t) local n = 0 for _, s in ipairs(f.prints) do if s:find(t, 1, true) then n = n + 1 end end return n end
local function lines(f, t) local o = {} for _, s in ipairs(f.prints) do if s:find(t, 1, true) then o[#o+1] = s end end return table.concat(o, " || ") end
do
  local f = F.new(path):load(); f.objects[1].tag = ""; f.area_objects = {20, 21, 1}
  f:arm(); f.env.OnRunScript("k_def_death01", 20)
  f.overrides.GetFirstPC = function() return 2 end
  f.env.OnModuleLoad()
  local a = f.objects[1].min_one_hp
  f:fire(#f.timers); local s = f.objects[1].min_one_hp
  f.env.OnScriptUnload()
  print(("R4-1L PC tag '' + swap + OnModuleLoad (IDs unchanged): after_load=%s after_settle=%s after_unload=%s pending=%d unload=%q")
    :format(tostring(a), tostring(s), tostring(f.objects[1].min_one_hp), nprint(f, "restore pending"), lines(f, "NOT restored")))
end
do
  local f = F.new(path):load()
  f.objects[3] = {tag = "twin", party = 1, x = 1, min_one_hp = 0}
  f.objects[4] = {tag = "twin", party = 1, x = 2, min_one_hp = 0}
  f.party = {1, 3, 4}; f.area_objects = {20, 21, 3, 4}
  f:arm(); f.env.OnRunScript("k_def_death01", 20)
  f.env.OnModuleLoad()
  print(("R4-2L same-tag pair across OnModuleLoad: after=%s,%s prior_unknown=%d pending=%d")
    :format(tostring(f.objects[3].min_one_hp), tostring(f.objects[4].min_one_hp), nprint(f, "prior unknown"), nprint(f, "restore pending")))
end
