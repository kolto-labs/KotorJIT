-- Adversarial probes for cursed/40_chain_reaction.lua under the repo fixture.
-- Run from worktree root: luajit <this> /tmp/kp-example-sources.lua
local F = dofile('tools/tests/examples/fixture.lua')
F.sources = assert(dofile(arg[1]))
local P='cursed/40_chain_reaction.lua'
local function report(name, ok, detail) print((ok and 'HOLDS ' or 'BREAKS')..'\t'..name..'\t'..tostring(detail or '')) end

-- A1: module transition changes party object IDs. Old id 2 disappears; new id 5
-- is the same party member re-created with the saved MinOneHP=1 flag.
do
  local f=F.new(P):load(); f:arm()
  f.env.OnRunScript('k_def_death01',20)              -- guards bastila(2): 0 -> 1
  local carried=f.objects[2].min_one_hp
  -- transition: engine serialises party; id 2 gone, id 5 is bastila with flag carried
  f.objects[5]={tag='bastila',party=1,x=1,min_one_hp=carried}; f.objects[2]=nil
  f.env.OnModuleLoad()
  report('A1 module load with new party IDs restores flag', f.objects[5].min_one_hp==0,
    'new-id bastila min_one_hp='..tostring(f.objects[5].min_one_hp)..' (prior was 0); SetMinOneHP calls='..f:count('SetMinOneHP'))
end

-- A2: invalid-object SetMinOneHP errors in bridge -> entry is kept forever; does it retry harmlessly?
do
  local f=F.new(P):load(); f:arm()
  f.env.OnRunScript('k_def_death01',20)
  f.overrides.SetMinOneHP=function(id) error('invalid object') end
  f.env.OnModuleLoad()
  f.overrides.SetMinOneHP=nil
  f:arm(); f.env.OnRunScript('k_def_death01',21)   -- id 2 still listed as guarded, guard() returns true without re-reading
  local reads=0; for _,c in ipairs(f.calls) do if c.name=='GetMinOneHP' then reads=reads+1 end end
  report('A2 failed restore is retried at the next disarm (f:arm calls OnModuleLoad)', reads==2 and f.objects[2].min_one_hp==1, 'GetMinOneHP reads='..reads)
end

-- A3: unload while the 3 s settle timer is pending. Unload restores; the late timer must do nothing harmful.
do
  local f=F.new(P):load(); f:arm()
  f.env.OnRunScript('k_def_death01',20)
  f.env.OnScriptUnload()
  local after_unload=f.objects[2].min_one_hp
  local n=f:count('SetMinOneHP')
  local r=f:fire(1)
  report('A3 unload during pending timer', after_unload==0 and f:count('SetMinOneHP')==n and r==false,
    'flag after unload='..tostring(after_unload)..', extra SetMinOneHP from late timer='..(f:count('SetMinOneHP')-n))
end

-- A4: re-entrant death during damage: nested detonate hits the same party member;
-- prior must still be the ORIGINAL value, not the protected 1.
do
  local f=F.new(P):load(); f.objects[2].min_one_hp=0; f:arm(); local re=false
  f.overrides.ApplyEffectToObject=function(d,e,id,s)
    f.apply_effect(id,e,d,s)
    if type(e)=='table' and e.effect=='EffectDamage' and id==2 and not re then re=true; f.env.OnRunScript('k_def_death01',21) end
  end
  f.env.OnRunScript('k_def_death01',20)
  local reads=f:count('GetMinOneHP')
  f:fire(#f.timers)
  report('A4 re-entrant detonation keeps original prior', f.objects[2].min_one_hp==0 and reads==1,
    'reads='..reads..' final='..tostring(f.objects[2].min_one_hp)..' timers='..#f.timers)
end

-- A5: re-entrant path where nested detonate fires restore? Nested settle timer from inner
-- blast is superseded by outer gen; latest gen is the outer one (inner increments first).
do
  local f=F.new(P):load(); f:arm(); local re=false
  f.overrides.ApplyEffectToObject=function(d,e,id,s)
    f.apply_effect(id,e,d,s)
    if type(e)=='table' and e.effect=='EffectDamage' and id==21 and not re then re=true; f.env.OnRunScript('k_def_death01',21) end
  end
  f.env.OnRunScript('k_def_death01',20)
  local gens={} for i,t in ipairs(f.timers) do gens[#gens+1]=t.data.gen end
  -- inner registers gen1, outer gen2: firing inner (1) must not restore, outer (2) must.
  f:fire(1); local mid=f.objects[2].min_one_hp; f:fire(2)
  report('A5 nested generations: only last timer restores', mid==1 and f.objects[2].min_one_hp==0, 'gens='..table.concat(gens,',')..' mid='..tostring(mid))
end

-- A6: bridge returns boolean false for GetMinOneHP (q's `ok and v or nil` idiom)
do
  local f=F.new(P,{GetMinOneHP=function() return false end}):load(); f:arm()
  f.env.OnRunScript('k_def_death01',20)
  report('A6 boolean-false prior treated as unreadable', f:count('SetMinOneHP')==0, 'SetMinOneHP='..f:count('SetMinOneHP')..' (party member excluded when bridge returns false)')
end

-- A7: SetMinOneHP succeeds for prot but EffectDamage is applied even when... check party dmg amount
do
  local f=F.new(P):load(); f:arm(); f.env.OnRunScript('k_def_death01',20)
  local amt; for _,c in ipairs(f.calls) do if c.name=='EffectDamage' then amt=amt or {} ; amt[#amt+1]=c.args[1] end end
  report('A7 party gets floor(40/3)=13', (function() for _,a in ipairs(amt) do if a==13 then return true end end end)(), 'amounts='..table.concat(amt,','))
end

-- A8: disarm on area enter restores while combat is continuing in same module
-- (area enter of another creature? OnAreaEnter fires for any entering object)
do
  local f=F.new(P):load(); f:arm(); f.env.OnRunScript('k_def_death01',20)
  f.env.OnAreaEnter(99,77,true)   -- some non-PC object enters the area
  report('A8 OnAreaEnter by any object disarms+restores', f.locals[5]==0, 'armed after non-PC OnAreaEnter='..tostring(f.locals[5])..' (pre-existing behaviour, not new)')
end
