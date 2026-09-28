-- Isolated adversarial probe: replace GetFirstPC after the original PC was
-- guarded, while retaining the original object.  Run with the project fixture.
local F = assert(loadfile("tools/tests/examples/fixture.lua"))()
F.sources = {
  ["scripts/examples/cursed/40_chain_reaction.lua"] = "scripts/examples/cursed/40_chain_reaction.lua",
}
local path = "scripts/examples/cursed/40_chain_reaction.lua"
local f = F.new(path):load()
f.area_objects = {20, 21, 2, 1}
f:arm()
f.env.OnRunScript("k_def_death01", 20)
assert(f.objects[1].min_one_hp == 1, "original PC was not guarded")
f.objects[7] = {tag="replacement", party=1, x=0, min_one_hp=1}
f.party = {7, 2}
f.overrides.GetFirstPC = function() return 7 end
f.env.OnModuleLoad()
print(("old_pc=%s replacement_pc=%s"):format(
  tostring(f.objects[1].min_one_hp), tostring(f.objects[7].min_one_hp)))
