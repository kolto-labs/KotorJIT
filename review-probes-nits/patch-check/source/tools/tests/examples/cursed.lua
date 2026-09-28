return function(test)
local specs={
 {'10_rancor_roulette.lua','k_def_percept01','roulette'},
 {'30_necromancer.lua','k_def_death01','necro'},
 {'40_chain_reaction.lua','k_def_death01','boom'},
 {'80_loot_pinata.lua','k_def_death01','pinata'},
}
for _,s in ipairs(specs) do
 test('cursed/'..s[1],'arming, eligible target, requests and duplicate guard',function(F,p)
  local f=F.new(p):load(); f.env.OnRunScript(s[2],20); assert(#f.timers==0 and f:count('ApplyEffectToObject')==0)
  f:arm(); f.env.OnRunScript('unrelated',20); f.env.OnRunScript(s[2],2); assert(#f.timers==0 and f:count('ApplyEffectToObject')==0)
  f.env.OnRunScript(s[2]..'\0',20); f.env.OnRunScript(s[2],20)
  if s[3]=='roulette' then
   assert(#f.timers==1 and f.timers[1].ms==50); assert(f:fire(1)==false)
   assert(f:last('EffectDisguise').args[1]==21); assert(f:last('SpeakString').caller==20)
  elseif s[3]=='necro' then
   assert(#f.timers==1 and f.timers[1].ms==800); f:fire(1)
   local c=f:last('CreateObject'); assert(c.args[1]==1 and c.args[2]=='g_sithtroop01')
   assert(f:last('DestroyObject').args[1]==20 and f:last('ActionAttack').caller==100)
   assert(f:fire(2)==false); assert(f:has('verify 100: valid=1'))
   f.env.OnRunScript(s[2],100); assert(#f.timers==2)
  elseif s[3]=='boom' then
   assert(f:last('SetMinOneHP').args[1]==2 and f:last('SetMinOneHP').args[2]==1)
   assert(f.locals[6]>0 and f:count('EffectDamage')==2)
  else
   assert(f:count('CreateObject')==5 and f:has('5 piles'))
   f.env.OnRunScript(s[2],21); assert(f:last('CreateObject').args[2]=='g_gizka01')
   assert(f:last('ActionAttack').caller==100)
  end
  assert(f.locals[7]==(s[3]=='pinata' and 2 or 1)); assert(f:has('[cursed:'..s[3]..']'))
 end)
 test('cursed/'..s[1],'conversation invalid and distant or party exclusions',function(F,p)
  local f=F.new(p):load(); f:arm(); f.overrides.GetIsInConversation=function() return 1 end
  f.env.OnRunScript(s[2],20); assert(#f.timers==0 and f:count('ApplyEffectToObject')==0)
  f.overrides.GetIsInConversation=function() return 0 end
  f.env.OnRunScript(s[2],F.INVALID); f.env.OnRunScript(s[2],1); f.env.OnRunScript(s[2],2)
  assert(#f.timers==0 and f:count('ApplyEffectToObject')==0)
 end)
end
test('cursed/20_fus_ro_dah.lua','five hits sweep eligible creatures and duplicate second',function(F,p)
 local f=F.new(p):load(); f.env.OnCreatureAttacked(20,1); assert(f:count('ApplyEffectToObject')==0); f:arm()
 f.env.OnCreatureAttacked(20,21); assert(f:count('ApplyEffectToObject')==0)
 for i=1,5 do f.second=i; f.env.OnCreatureAttacked(20,1); local n=f:count('EffectForcePushed'); f.env.OnCreatureAttacked(20,1); assert(f:count('EffectForcePushed')==n) end
 assert(f.locals[7]==5 and f:count('EffectForcePushed')==6)
 assert(f:has('FUS RO DAH: 1 flung') and f:last('SpeakString').caller==1)
end)
local wheel={'EffectWhirlWind','EffectChoke','EffectHorrified','EffectDisguise','EffectBeam','EffectHaste','EffectDamageShield','EffectHeal','EffectStunned','JumpToLocation'}
for i,name in ipairs(wheel) do test('cursed/50_chaos_roulette.lua','wheel branch '..i,function(F,p)
 local f=F.new(p):load(); f:arm(); f.random=i
 f.env.OnRunScript('unrelated',20); assert(f:count(name)==0)
 f.env.OnRunScript('k_def_combend01',20); assert(f:count(name)==1 and f.locals[7]==1)
 assert(f:last('SpeakString').caller==20)
 if i==10 then assert(f:last(name).caller==20) else assert(f:last('ApplyEffectToObject').args[3]==20) end
 f.objects[20].dead=1; f.env.OnRunScript('k_def_combend01',20); assert(f.locals[7]==1)
end) end
test('cursed/60_rave.lua','one repeating timer, dance scope, fourth beat plasma',function(F,p)
 local f=F.new(p):load(); f.env.OnTick(1); f.env.OnTick(2); assert(#f.timers==1 and f.timers[1].ms==700)
 for i=1,4 do assert(f:fire(1)==true) end
 assert(f.locals[7]==4 and f:count('MusicBattlePlay')==1 and f:count('ActionPlayAnimation')==3)
 assert(f:last('ActionPlayAnimation').caller==20 and f:last('EffectVisualEffect').args[1]==3010)
 f.objects[1].dead=1; local n=#f.calls; assert(f:fire(1)==true); assert(f.locals[7]==4)
end)
test('cursed/70_doppelganger.lua','PC and hostile disguises once, party exclusion',function(F,p)
 local f=F.new(p):load(); f:arm(); f.env.OnCreatureAttacked(20,21); assert(f:count('EffectDisguise')==0)
 f.env.OnCreatureAttacked(1,20); assert(f:count('EffectDisguise')==2 and f.locals[7]==1)
 assert(f:last('EffectDisguise').args[1]==6 and f:last('SpeakString').caller==20)
 f.env.OnCreatureAttacked(20,1); f.env.OnCreatureAttacked(2,1); assert(f:count('EffectDisguise')==2)
end)
test('cursed/90_bullet_time.lua','HP threshold, active suppression and previous speed restore',function(F,p)
 local f=F.new(p):load(); f.speed=1.5; f.env.OnTick(5); f.hp=80; f.env.OnTick(10); assert(#f.timers==0)
 f.hp=69; f.env.OnTick(15); assert(f.speed==.25 and f.locals[6]==25 and f.locals[7]==1)
 assert(f.timers[1].ms==2500); f.hp=30; f.env.OnTick(20); assert(#f.timers==1)
 assert(f:fire(1)==false and f.speed==1.5 and f:has('released'))
end)
test('cursed/100_item_airstrike.lua','owner filtering, strike radius and level-up requests',function(F,p)
 local f=F.new(p):load(); f.env.OnModuleAcquireItem(40); assert(f:count('EffectDamage')==0); f:arm()
 f.objects[21].x=21; f.env.OnModuleAcquireItem(40); assert(f.locals[7]==1 and f.locals[6]==1)
 local c=f:last('EffectDamage'); assert(c.args[1]==60 and c.args[2]==2048)
 f.env.OnModuleAcquireItem(40); assert(f.locals[7]==1)
 f.env.OnModulePlayerLevelUp(1); assert(f:last('EffectDisguise').args[1]==22 and f:last('ApplyEffectToObject').args[4]==15)
end)
test('cursed/80_loot_pinata.lua','retry after position temporarily unavailable',function(F,p)
 local f=F.new(p):load(); f:arm(); f.overrides.GetPosition=function() return nil end
 f.env.OnRunScript('k_def_death01',20); assert(f:count('CreateObject')==0)
 f.overrides.GetPosition=nil; f.env.OnRunScript('k_def_death01',20); assert(f:count('CreateObject')==5)
end)
test('cursed/100_item_airstrike.lua','unrelated owner does not consume later legitimate pickup',function(F,p)
 local f=F.new(p):load(); f:arm(); f.overrides.GetItemPossessor=function() return 20 end
 f.env.OnModuleAcquireItem(40); assert(f:count('EffectDamage')==0)
 f.overrides.GetItemPossessor=nil; f.env.OnModuleAcquireItem(40); assert(f.locals[7]==1)
end)
test('cursed/20_fus_ro_dah.lua','failed time read does not permanently deduplicate victim',function(F,p)
 local f=F.new(p,{GetTimeSecond=function() error('clock unavailable') end}):load(); f:arm()
 f.env.OnCreatureAttacked(20,1); f.env.OnCreatureAttacked(20,1); assert(f.locals[7]==2)
end)
test('cursed/70_doppelganger.lua','failed disguise can be retried without false copy count',function(F,p)
 local f=F.new(p,{EffectDisguise=function() return nil end}):load(); f:arm()
 f.env.OnCreatureAttacked(20,1); assert(f.locals[7]==nil and not f:has('wears your face'))
 f.overrides.EffectDisguise=nil; f.env.OnCreatureAttacked(20,1); assert(f.locals[7]==1)
end)
test('cursed/60_rave.lua','dead PC does not start timer',function(F,p)
 local f=F.new(p):load(); f.objects[1].dead=1; f.env.OnTick(1); assert(#f.timers==0)
 f.objects[1].dead=0; f.env.OnTick(2); assert(#f.timers==1)
end)
test('cursed/40_chain_reaction.lua','transient inner PC failure allows retry',function(F,p)
 local f=F.new(p):load(); f:arm(); local reads=0
 f.overrides.GetFirstPC=function() reads=reads+1; if reads==3 then return nil end return 1 end
 f.env.OnRunScript('k_def_death01',20); assert(f.locals[7]==nil)
 f.overrides.GetFirstPC=nil; f.env.OnRunScript('k_def_death01',20); assert(f.locals[7]==1)
end)

end
