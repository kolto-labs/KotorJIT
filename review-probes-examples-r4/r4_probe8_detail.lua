-- R4-8 detail: which path writes member 5? PC tag '', untagged member 5 (genuine 1) becomes GetFirstPC.
local F = assert(loadfile("tools/tests/examples/fixture.lua"))()
local path = "scripts/examples/cursed/40_chain_reaction.lua"
F.sources = { [path] = arg and arg[1] or path }
local f = F.new(path):load(); f.objects[1].tag = ""; f.area_objects = {20, 21, 1}
f:arm(); f.env.OnRunScript("k_def_death01", 20)
f.objects[5] = {tag = "", party = 1, x = 2, min_one_hp = 1}
f.party = {1, 2, 5}; f.overrides.GetFirstPC = function() return 5 end
local b = #f.calls
f.env.OnAreaEnter(99, 31)   -- same module, IDs unchanged, PC 1 still valid
local o = {} for i = b + 1, #f.calls do local c = f.calls[i] if c.name == "SetMinOneHP" then o[#o+1] = c.args[1].."<-"..c.args[2] end end
local logs = {} for _, s in ipairs(f.prints) do if s:find("min-one-HP", 1, true) then logs[#logs+1] = s end end
print(("R4-8d same-module OnAreaEnter, control on untagged member 5: sets=[%s] pc1=%s member5=%s logs=%d")
  :format(table.concat(o, " "), tostring(f.objects[1].min_one_hp), tostring(f.objects[5].min_one_hp), #logs))
