-- Mutation + anomaly probes. luajit mutations.lua /tmp/kp-example-sources.lua
local F = dofile('tools/tests/examples/fixture.lua')
F.sources = assert(dofile(arg[1]))
local function src(p) local h=assert(io.open(F.sources[p])); local s=h:read('*a'); h:close(); return s end
local function out(n,ok,d) print((ok and 'HOLDS ' or 'BREAKS')..'\t'..n..'\t'..tostring(d or '')) end
-- M1: chain without restore in disarm -> the writer's transition assertion should catch it
do
  local p='cursed/40_chain_reaction.lua'; local s=src(p)
  local m=s:gsub('local function disarm%(%)\n  restore_guards%(%)','local function disarm()',1)
  assert(m~=s,'mutation not applied')
  local f=F.new(p):load(m); f.objects[3]={tag='carth',party=1,x=2}; f.area_objects={20,21,2,3}; f:arm()
  f.env.OnRunScript('k_def_death01',20); f.env.OnModuleLoad()
  out('M1 transition restore is load-bearing (mutant keeps flag=1)', f.objects[3].min_one_hp==1, 'mutant flag='..tostring(f.objects[3].min_one_hp))
end
-- M2: airstrike under the 2026-09-16 anomaly: GetIsEnemy answers 0 inside the hook
do
  local p='cursed/100_item_airstrike.lua'
  local f=F.new(p,{GetIsEnemy=function() return 0 end}):load(); f:arm(); f.env.OnModuleAcquireItem(40)
  local dmg=0; for _,c in ipairs(f.calls) do if c.name=='EffectDamage' then dmg=dmg+1 end end
  out('M2 anomaly => current bytes strike nothing', dmg==0, 'EffectDamage calls='..dmg..', local7='..tostring(f.locals[7]))
end
-- M3: prior bytes (HEAD) under the same anomaly still struck non-party creatures
do
  local p='cursed/100_item_airstrike.lua'; local h=assert(io.open(arg[2])); local s=h:read('*a'); h:close()
  local f=F.new(p,{GetIsEnemy=function() return 0 end}):load(s); f:arm(); f.env.OnModuleAcquireItem(40)
  local dmg=0; for _,c in ipairs(f.calls) do if c.name=='EffectDamage' then dmg=dmg+1 end end
  out('M3 HEAD bytes under anomaly still strike', dmg>0, 'EffectDamage calls='..dmg)
end
