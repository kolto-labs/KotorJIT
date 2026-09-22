return function(test)
local p='showcase/30_battle_meditation.lua'
test(p,'void count, suppression and next round',function(F,p)
 local f=F.new(p):load(); f.env.OnRunScript('k_def_attacked01\0',1,1,true)
 assert(f:count('ApplyEffectToObject')==2); assert(f:has('steadied 2 of the party'))
 local c=f:last('ApplyEffectToObject'); assert(c.args[1]==1 and c.args[3]==2 and c.args[4]==6)
 f.env.OnRunScript('k_def_attacked01',1); assert(f:count('ApplyEffectToObject')==2)
 f.env.OnRunScript('k_def_combend01',1); f.env.OnRunScript('k_def_attacked01',1)
 assert(f:has('round 2: steadied 2'))
end)
for _,mode in ipairs({'absent','dead','nonparty','invalid-party','nonparty-victim','wrong-script','constructor-error','apply-error','fallback'}) do
 test(p,mode,function(F,p)
  local f=F.new(p)
  if mode=='absent' then f.objects[2]=nil; f.party={1}
  elseif mode=='dead' then f.objects[2].dead=1
  elseif mode=='nonparty' then f.objects[2].party=0; f.party={1}
  elseif mode=='invalid-party' then f.objects[2]=nil
  elseif mode=='constructor-error' then f.overrides.EffectAttackIncrease=function() error('unsupported') end
  elseif mode=='apply-error' then f.overrides.ApplyEffectToObject=function() error('VM unavailable') end
  elseif mode=='fallback' then f.overrides.GetObjectByTag=function() return F.INVALID end end
  f:load(); f.env.OnRunScript(mode=='wrong-script' and 'other' or 'k_def_attacked01',mode=='nonparty-victim' and 20 or 1)
  if mode=='fallback' then assert(f:has('steadied 2'))
  elseif mode=='apply-error' then assert(f:has('steadied 0'))
  else assert(f:count('ApplyEffectToObject')==0) end
 end)
end
test('showcase/10_ahto_city_law.lua','module attacker guards and persisted strikes',function(F,p)
 local f=F.new(p):load(); f.env.OnRunScript('k_def_attacked01',20); assert(#f.prints==0)
 f.module='manm26ad'; for i=1,3 do f.env.OnRunScript('k_def_attacked01\0',20) end
 assert(f:count('SpeakString')==2 and f.env.OnSave()=='3')
 local g=F.new(p):load(); g.module=f.module; g.env.OnLoad(f.env.OnSave()); g.env.OnRunScript('k_def_attacked01',20); assert(g:has('strike 4'))
 g.overrides.GetLastAttacker=function() return 21 end; g.env.OnRunScript('k_def_attacked01',20); assert(#g.prints==1)
end)
test('showcase/20_sith_patrol_alarm.lua','hostility and once per sentry per module',function(F,p)
 local f=F.new(p,{GetIsEnemy=function() return 0 end}):load(); f.env.OnRunScript('k_def_percept01',20); assert(#f.prints==0)
 f.overrides.GetIsEnemy=function() return 1 end
 f.env.OnRunScript('k_def_percept01\0',20); f.env.OnRunScript('k_def_percept01',20); assert(f:count('SpeakString')==1)
 f.module='end_m01aa'; f.env.OnRunScript('k_def_percept01',20); assert(f:has('(2 so far)'))
end)
test('showcase/40_alignment_drift.lua','poll and decade crossings in both directions',function(F,p)
 local f=F.new(p):load(); f.env.OnTick(179); assert(#f.calls==0)
 f.alignment=59; f.env.OnTick(180); f.alignment=60; f.env.OnTick(360); assert(f:has('+1, now 60'))
 f.alignment=59; f.env.OnTick(540); assert(f:has('-1, now 59'))
 f.alignment=58; f.env.OnTick(720); assert(#f.prints==2)
 f.overrides.GetGoodEvilValue=function() return 'bad' end; f.env.OnTick(900); assert(#f.prints==2)
end)
test('showcase/50_enclave_arrival.lua','prefix deduplication and save reload',function(F,p)
 local f=F.new(p):load(); f.env.OnTick(44); assert(#f.calls==0); f.env.OnTick(45); assert(f:has('[arrival] dan'))
 f.module='danm14'; f.env.OnTick(90); assert(#f.prints==1)
 local g=F.new(p):load(); g.env.OnLoad(f.env.OnSave()); g.env.OnTick(45); assert(#g.prints==0)
 g.module='manm26ad'; g.env.OnTick(90); assert(g:has('[arrival] man'))
 g.module='unknown'; g.env.OnTick(135); assert(#g.prints==1)
end)
test('showcase/60_party_wounded.lua','threshold, party exclusion and duplicate suppression',function(F,p)
 local f=F.new(p):load(); f.hp=36; f.env.OnRunScript('k_def_damage01',2); assert(#f.prints==0)
 f.hp=35; f.env.OnRunScript('k_def_damage01',20); assert(#f.prints==0)
 f.env.OnRunScript('k_def_damage01\0',2); assert(f:last('SpeakString').args[1]=='Bastila! Stay with us!')
 f.env.OnRunScript('k_def_damage01',2); assert(#f.prints==1)
end)
test('showcase/60_party_wounded.lua','padded engine tag preserves full native oracle',function(F,p)
 local f=F.new(p,{GetTag=function() return "bastila\0\0" end}):load()
 f.hp=35; f.env.OnRunScript('k_def_damage01',2)
 -- Native log sinks terminate at NUL even though Lua strings retain it.
 local native_line=(f.prints[1] or ''):match('^[^%z]*')
 assert(native_line=='[wounded] bastila below 35%')
 assert(f:last('SpeakString').args[1]=='Bastila! Stay with us!')
end)

end
