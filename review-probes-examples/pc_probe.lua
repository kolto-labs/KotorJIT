local F = dofile('tools/tests/examples/fixture.lua')
F.sources = assert(dofile(arg[1]))
local P='cursed/40_chain_reaction.lua'
local function out(n,ok,d) print((ok and 'HOLDS ' or 'BREAKS')..'\t'..n..'\t'..tostring(d or '')) end
-- P1: PC in blast radius is guarded and restored at settle
do local f=F.new(P):load(); f.area_objects={20,21,2,1}; f:arm(); f.env.OnRunScript('k_def_death01',20)
  local during=f.objects[1].min_one_hp; f:fire(#f.timers)
  out('P1 PC guarded then restored at settle', during==1 and f.objects[1].min_one_hp==0, 'during='..tostring(during)..' after='..tostring(f.objects[1].min_one_hp)) end
-- P2 (A3 with PC): unload with pending timer restores PC
do local f=F.new(P):load(); f.area_objects={20,21,2,1}; f:arm(); f.env.OnRunScript('k_def_death01',20); f.env.OnScriptUnload()
  local n=f:count('SetMinOneHP'); f:fire(1)
  out('P2 PC restored on unload; late timer inert', f.objects[1].min_one_hp==0 and f:count('SetMinOneHP')==n, 'after='..tostring(f.objects[1].min_one_hp)) end
-- P3 (A1 with PC): PC gets a new object id across module load
do local f=F.new(P):load(); f.area_objects={20,21,2,1}; f:arm(); f.env.OnRunScript('k_def_death01',20)
  f.objects[7]={tag='pc',party=1,x=0,min_one_hp=f.objects[1].min_one_hp}; f.objects[1]=nil
  f.overrides.GetFirstPC=function() return 7 end
  f.env.OnModuleLoad()
  out('P3 PC with new id after module load is restored', f.objects[7].min_one_hp==0, 'new-id PC min_one_hp='..tostring(f.objects[7].min_one_hp)) end
