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
test('cursed/70_doppelganger.lua','captures pre-Malak row including row zero for three copies and removes only retained constructor tokens',function(F,p)
 local f=F.new(p):load(); f.objects[22]={tag='sith3',x=7,appearance=30}; f.objects[23]={tag='dead',x=9,appearance=31,dead=1}; f:arm()
 f.env.OnCreatureAttacked(20,21); assert(f:count('EffectDisguise')==0)
 f.env.OnCreatureAttacked(1,20)
 assert(f:appearance(1)==21 and f:appearance(20)==136 and f.locals[7]==1)
 f.env.OnCreatureAttacked(21,1); f.env.OnCreatureAttacked(1,22)
 assert(f:appearance(21)==136 and f:appearance(22)==136 and f.locals[7]==3)
 local effects=f:count('EffectDisguise')
 f.env.OnCreatureAttacked(20,1); f.env.OnCreatureAttacked(2,1)
 f.env.OnCreatureAttacked(20,21); f.env.OnCreatureAttacked(1,F.INVALID)
 f.env.OnCreatureAttacked(1,23)
 assert(f:count('EffectDisguise')==effects and f.locals[7]==3 and f:appearance(20)==136)
 f.objects[1].combat=1; f.env.OnTick(201); f.objects[1].combat=0
 for tick=202,241 do f.env.OnTick(tick) end
 assert(f:appearance(1)==136 and f:appearance(20)==28 and f:appearance(21)==29 and f:appearance(22)==30 and f.locals[5]==0 and f.locals[7]==0)
 local zero=F.new(p):load(); zero.objects[1].appearance=0; zero:arm(); zero.env.OnCreatureAttacked(20,1)
 assert(zero:appearance(1)==21 and zero:appearance(20)==0 and zero.locals[7]==1)
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
test('cursed/70_doppelganger.lua','baseline identical disguise survives exact constructor-token cleanup and fresh wrappers are never compared',function(F,p)
 local f=F.new(p):load()
 f.objects[20].appearance=55
 local baseline=f.env.nwscript.call('EffectDisguise',55); f.env.nwscript.call('ApplyEffectToObject',2,baseline,1,0)
 local hostile_baseline=f.env.nwscript.call('EffectDisguise',55); f.env.nwscript.call('ApplyEffectToObject',2,hostile_baseline,20,0)
 local first=f.env.nwscript.call('GetFirstEffect',1); local again=f.env.nwscript.call('GetFirstEffect',1)
 assert(first~=again and f.env.nwscript.call('GetIsEffectValid',first)==1 and f.env.nwscript.call('GetIsEffectValid',again)==1)
 collectgarbage('collect')
 f:arm(); f.env.OnCreatureAttacked(20,1)
 assert(f:appearance(1)==21 and f:appearance(20)==55 and f:active_disguises(1)==2 and f:active_disguises(20)==2 and f:count('RemoveEffect')==0)
 f.objects[1].combat=1; f.env.OnTick(201); f.objects[1].combat=0
 for tick=202,241 do f.env.OnTick(tick) end
 assert(f:appearance(1)==55 and f:appearance(20)==55 and f:active_disguises(1)==1 and f:active_disguises(20)==1 and f:count('RemoveEffect')==2)
 f.env.nwscript.call('RemoveEffect',20,hostile_baseline)
 assert(f:active_disguises(20)==0 and f:appearance(20)==55 and f:count('RemoveEffect')==3)
end)
test('cursed/70_doppelganger.lua','post-apply throw and failed cleanup retain token ownership until retry or terminal transition',function(F,p)
 local f=F.new(p):load(); f:arm()
 f.overrides.ApplyEffectToObject=function(duration,effect,id,seconds) f.apply_effect(id,effect,duration,seconds); error('mutated then threw') end
 f.overrides.RemoveEffect=function() error('controlled removal failure') end
 f.env.OnCreatureAttacked(20,1)
 assert(f:appearance(1)==21 and f:appearance(20)==28 and f.locals[7]==0)
 f.env.OnCreatureAttacked(21,1); assert(f:appearance(21)==29 and f:count('EffectDisguise')==1)
 f.env.OnTick(201); assert(f.locals[5]==1 and f:appearance(1)==21)
 f.overrides.ApplyEffectToObject=nil; f.overrides.RemoveEffect=nil; f.env.OnTick(202)
 assert(f:appearance(1)==136 and f.locals[5]==0 and f.locals[7]==0)
 f:arm(); f.env.OnCreatureAttacked(20,1); f.objects[1]=nil; f.env.OnTick(201)
 assert(f.locals[5]==1 and f:has('actor unavailable'))
 f.env.OnModuleLoad(); assert(f.locals[5]==0 and f:has('transition terminal: unavailable actor was not restored'))
 for tick=1,200 do f.env.OnTick(tick) end; assert(f.locals[5]==1)
end)
test('cursed/70_doppelganger.lua','same-row removal failure retains the exact token until a successful retry',function(F,p)
 local f=F.new(p):load(); f.objects[20].appearance=136; f:arm(); f.env.OnCreatureAttacked(20,1)
 assert(f:appearance(20)==136 and f:active_disguises(20)==1)
 f.overrides.RemoveEffect=function() error('same-row removal failure') end
 f.objects[1].combat=1; f.env.OnTick(201); f.objects[1].combat=0
 for tick=202,241 do f.env.OnTick(tick) end
 assert(f:active_disguises(20)==1 and f:count('RemoveEffect')>=2 and f.locals[5]==1)
 f.overrides.RemoveEffect=nil; f.env.OnTick(242)
 assert(f:active_disguises(20)==0 and f.locals[5]==0)
end)
test('cursed/70_doppelganger.lua','area and module transitions restore PC and three surviving copies before rearming',function(F,p)
 local function populated()
  local f=F.new(p):load(); f.objects[22]={tag='sith3',x=7,appearance=30}; f:arm()
  f.env.OnCreatureAttacked(20,1); f.env.OnCreatureAttacked(21,1); f.env.OnCreatureAttacked(22,1)
  assert(f:appearance(1)==21 and f:appearance(20)==136 and f:appearance(21)==136 and f:appearance(22)==136)
  return f
 end
 local area=populated(); area.env.OnAreaEnter(99,1,true)
 assert(area:appearance(1)==136 and area:appearance(20)==28 and area:appearance(21)==29 and area:appearance(22)==30 and area.locals[5]==0)
 local module=populated(); module.env.OnModuleLoad()
 assert(module:appearance(1)==136 and module:appearance(20)==28 and module:appearance(21)==29 and module:appearance(22)==30 and module.locals[5]==0)
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

test('cursed/40_chain_reaction.lua','party min-one-HP guard restores each prior flag after settle, transition and unload',function(F,p)
 local f=F.new(p):load(); f.objects[2].min_one_hp=1; f.objects[3]={tag='carth',party=1,x=2}
 f.objects[22]={tag='sith3',x=6}; f.objects[23]={tag='sith4',x=4}; f.area_objects={20,21,2,3,22,23}; f:arm()
 local function order(id)
  local read,set
  for i,c in ipairs(f.calls) do
   if c.name=='GetMinOneHP' and c.args[1]==id then read=read or i end
   if c.name=='SetMinOneHP' and c.args[1]==id then set=set or i end
  end
  return read,set
 end
 f.env.OnRunScript('k_def_death01',20)
 local read,set=order(3); assert(read and set and read<set, 'prior flag must be read before protection')
 assert(f.objects[2].min_one_hp==1 and f.objects[3].min_one_hp==1)
 assert(#f.timers==1 and f.timers[1].name=='chain_settle')
 assert(f:fire(1)==false)
 assert(f.objects[2].min_one_hp==1 and f.objects[3].min_one_hp==0, 'settle restores each prior flag')
 f.env.OnRunScript('k_def_death01',21); f.env.OnRunScript('k_def_death01',22)
 assert(#f.timers==3 and f.objects[3].min_one_hp==1)
 assert(f:fire(2)==false and f.objects[3].min_one_hp==1, 'a superseded settle timer restores nothing')
 assert(f:fire(3)==false and f.objects[3].min_one_hp==0 and f.objects[2].min_one_hp==1)
 f.env.OnRunScript('k_def_death01',23); assert(f.objects[3].min_one_hp==1)
 f.env.OnModuleLoad(); assert(f.objects[3].min_one_hp==0 and f.objects[2].min_one_hp==1, 'transition restores')
 f:arm(); f.objects[24]={tag='sith5',x=3}; f.env.OnRunScript('k_def_death01',24); assert(f.objects[3].min_one_hp==1)
 f.env.OnScriptUnload(); assert(f.objects[3].min_one_hp==0 and f.objects[2].min_one_hp==1, 'unload restores')
end)
test('cursed/40_chain_reaction.lua','unreadable prior min-one-HP flag leaves that party member untouched',function(F,p)
 local f=F.new(p,{GetMinOneHP=function() error('bridge refused') end}):load(); f:arm()
 f.env.OnRunScript('k_def_death01',20)
 assert(f:count('SetMinOneHP')==0 and f.objects[2].min_one_hp==nil)
 for _,c in ipairs(f.calls) do if c.name=='ApplyEffectToObject' then assert(c.args[3]~=2,'party member damaged without a restorable guard') end end
 assert(f:count('EffectDamage')==1 and f.locals[7]==1)
end)
local function vfx_rows(f) local rows={} for _,c in ipairs(f.calls) do if c.name=='EffectVisualEffect' then rows[#rows+1]=c.args[1] end end return rows end
test('cursed/40_chain_reaction.lua','frag VFX is unreachable when blast deaths arrive after the hook returns',function(F,p)
 local f=F.new(p):load(); f:arm()
 f.env.OnRunScript('k_def_death01',20); f.env.OnRunScript('k_def_death01',21)
 local rows=vfx_rows(f); assert(#rows==2 and rows[1]==3005 and rows[2]==3005, 'deferred chain uses thermal only')
 assert(f.locals[7]==2)
end)
test('cursed/40_chain_reaction.lua','frag VFX is reached only if a death script re-enters during the damage call',function(F,p)
 local f=F.new(p):load(); f:arm(); local reentered=false
 f.overrides.ApplyEffectToObject=function(duration,effect,id,seconds)
  f.apply_effect(id,effect,duration,seconds)
  if type(effect)=='table' and effect.effect=='EffectDamage' and id==21 and not reentered then reentered=true; f.env.OnRunScript('k_def_death01',21) end
 end
 f.env.OnRunScript('k_def_death01',20)
 local rows=vfx_rows(f); assert(#rows==2 and rows[1]==3005 and rows[2]==3003, 'synchronous re-entry uses frag')
 assert(f.locals[7]==2)
end)
test('cursed/100_item_airstrike.lua','strikes only hostile non-party creatures by GetIsEnemy against the PC',function(F,p)
 local f=F.new(p):load(); f.objects[22]={tag='neutral',x=4,appearance=6}; f.area_objects={20,21,2,22}
 f.overrides.GetIsEnemy=function(target,source) assert(source==1,'hostility is judged against the PC'); return (target==20 or target==21) and 1 or 0 end
 f:arm(); f.env.OnModuleAcquireItem(40)
 local struck={}
 for _,c in ipairs(f.calls) do if c.name=='ApplyEffectToObject' and type(c.args[2])=='table' and c.args[2].effect=='EffectDamage' then struck[c.args[3]]=true end end
 assert(struck[20] and struck[21] and not struck[22] and not struck[2], 'neutral and party excluded')
 assert(f.locals[6]==2 and f.locals[7]==1)
 local asked=false; for _,c in ipairs(f.calls) do if c.name=='GetIsEnemy' and c.args[1]==22 and c.args[2]==1 then asked=true end end; assert(asked)
end)

end
