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
   assert(f:count('EffectDamage')==1 and f:last('EffectDamage').args[1]==40 and f.locals[6]==nil)
   for _,c in ipairs(f.calls) do if c.name=='ApplyEffectToObject' then assert(c.args[3]~=1 and c.args[3]~=2,'party member in the blast') end end
   assert(f:count('SetMinOneHP')==0 and f:count('GetMinOneHP')==0)
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

-- Round 5 (redesign): the script never touches min-one-HP. The PC and the
-- party are left out of every blast, judged at blast time by GetFirstPC and
-- IsObjectPartyMember. The oracle below reads the fixture's own truth at the
-- moment each effect lands, not anything the script remembers.
local CHAIN='cursed/40_chain_reaction.lua'
local function protected_now(f,id)
 local pc=(f.overrides.GetFirstPC or function() return 1 end)()
 return id==pc or (f.objects[id]~=nil and f.objects[id].party==1)
end
-- Recorded, not asserted, in the override: the script calls through pcall,
-- so an error raised here would be swallowed.
local function watch(f)
 f.damaged, f.violations = {}, {}
 f.overrides.ApplyEffectToObject=function(duration,effect,id,seconds)
  if protected_now(f,id) then f.violations[#f.violations+1]=id end
  if type(effect)=='table' and effect.effect=='EffectDamage' then f.damaged[id]=(f.damaged[id] or 0)+1 end
  f.apply_effect(id,effect,duration,seconds)
 end
 return f
end
local function flags(f,expect)
 assert(#f.violations==0,'an effect reached the PC or a party member: '..tostring(f.violations[1]))
 assert(f:count('SetMinOneHP')==0 and f:count('GetMinOneHP')==0,'a min-one-HP routine was called')
 for id,v in pairs(expect) do assert(f.objects[id] and f.objects[id].min_one_hp==v,'min-one-HP flag changed on '..id) end
end
local function rearm_in_module(f) for i=1,200 do f.env.OnTick(i,true) end assert(f.locals[5]==1) end
test(CHAIN,'static: the script never names a min-one-HP routine, reaches NWScript only through nwscript.call and has no Lua name that is an NWScript routine',function(F,p)
 local src=assert(io.open(F.source(p))):read('*a')
 assert(not src:find('MinOneHP',1,true),'a min-one-HP routine is named in the script')
 for ref in src:gmatch('nwscript%.([%w_]+)') do assert(ref=='call','nwscript.'..ref..' used') end
 local catalog=assert(io.open('src/generated/routines_k1.inc')):read('*a')
 local names={}
 for n in src:gmatch('function%s+([%w_]+)') do names[n]=true end
 for n in src:gmatch('local%s+([%w_]+)') do if n~='function' then names[n]=true end end
 for n in pairs(names) do assert(not catalog:find('"'..n..'"',1,true),'Lua name duplicates an NWScript routine: '..n) end
 assert(names.spared and names.in_party and names.detonate,'name scan found nothing')
end)
test(CHAIN,'hostiles chain; the PC, a tagged member and an untagged member are never hit and their flags are never read or set',function(F,p)
 local f=watch(F.new(p):load())
 f.objects[1].min_one_hp=0; f.objects[2].min_one_hp=1
 f.objects[3]={tag='',party=1,x=2,min_one_hp=0}; f.objects[22]={tag='sith3',x=6}
 f.party={1,2,3}; f.area_objects={20,21,2,3,22,1}; f:arm()
 f.env.OnRunScript('k_def_death01',20)
 assert(f.damaged[21]==1 and f.damaged[22]==1 and f:has('sith detonated: 2 hit (#1)'))
 f.objects[20].dead=1; f.env.OnRunScript('k_def_death01',21)
 assert(f.damaged[22]==2 and f:has('sith2 detonated: 1 hit (#2)') and f.locals[7]==2,'hostiles did not chain')
 for _,id in ipairs({1,2,3}) do f.env.OnRunScript('k_def_death01',id) end
 assert(f.locals[7]==2,'a party death detonated')
 assert(not f.damaged[1] and not f.damaged[2] and not f.damaged[3])
 assert(f.locals[6]==nil,'party damage is no longer published')
 flags(f,{[1]=0,[2]=1,[3]=0})
end)
test(CHAIN,'after a module load: a member re-created under a new ID is left out, an old party ID now on a hostile is hit, and a recycled corpse ID detonates again',function(F,p)
 local f=watch(F.new(p):load()); f.objects[2].min_one_hp=0; f:arm()
 f.env.OnRunScript('k_def_death01',20); assert(f.damaged[21]==1 and not f.damaged[2])
 f.env.OnModuleLoad()
 f.objects[5]={tag='bastila',party=1,x=4,min_one_hp=1}; f.objects[2]={tag='rakghoul',x=4}
 f.objects[21]={tag='carth',party=1,x=5,min_one_hp=0}; f.objects[20]={tag='sith',x=3}
 f.party={1,5,21}; f.area_objects={20,2,5,21,1}; f.damaged={}
 f:arm(); f.env.OnRunScript('k_def_death01',20)
 assert(f.locals[7]==2,'a corpse under an ID used in the last module never detonated (R4-7)')
 assert(f.damaged[2]==1 and not f.damaged[5] and not f.damaged[21] and not f.damaged[1])
 flags(f,{[5]=1,[21]=0})
end)
test(CHAIN,'a leader swap changes nothing: GetFirstPC and party membership each keep a creature out on their own',function(F,p)
 local f=watch(F.new(p):load()); f.objects[1].min_one_hp=1; f.objects[2].min_one_hp=0
 f.area_objects={20,21,2,1}; f:arm()
 f.overrides.GetFirstPC=function() return 2 end
 f.env.OnRunScript('k_def_death01',20)
 assert(f.damaged[21]==1 and not f.damaged[1] and not f.damaged[2])
 -- The controlled creature answers "not a party member": GetFirstPC alone keeps it out.
 f.objects[9]={tag='',party=0,x=4,min_one_hp=0}; f.party={1,2}
 f.overrides.GetFirstPC=function() return 9 end
 f.area_objects={21,9,1,2}; f.objects[20].dead=1
 f.env.OnRunScript('k_def_death01',21)
 assert(f.locals[7]==2 and not f.damaged[9] and not f.damaged[1] and not f.damaged[2])
 f.env.OnRunScript('k_def_death01',9); assert(f.locals[7]==2,'the controlled creature detonated')
 flags(f,{[1]=1,[2]=0,[9]=0})
end)
test(CHAIN,'within one module, membership and control are read again at every blast: a member who left is hit, a hostile who joined and a new member are spared, a former leader is hit',function(F,p)
 local f=watch(F.new(p):load()); f.objects[2].min_one_hp=0
 f.objects[9]={tag='',party=0,x=4}; f.objects[22]={tag='sith3',x=6}
 f.area_objects={20,21,2,22,9,1}; f:arm()
 f.overrides.GetFirstPC=function() return 9 end
 f.env.OnRunScript('k_def_death01',20)
 assert(f.damaged[21]==1 and f.damaged[22]==1 and not f.damaged[9] and not f.damaged[2] and not f.damaged[1])
 -- No module load: bastila leaves, hostile 21 joins, a new member 5 appears, control goes back to the PC.
 f.objects[2].party=0; f.objects[21].party=1; f.objects[5]={tag='mission',party=1,x=4,min_one_hp=0}
 f.party={1,21,5}; f.overrides.GetFirstPC=nil; f.objects[20].dead=1
 f.objects[23]={tag='sith4',x=4}; f.area_objects={23,21,2,22,9,5,1}
 f.env.OnRunScript('k_def_death01',23)
 assert(f.locals[7]==2)
 assert(f.damaged[2]==1,'a member who left the party was still spared')
 assert(f.damaged[9]==1,'the former leader was still spared')
 assert(f.damaged[21]==1 and not f.damaged[5] and not f.damaged[1],'a creature who joined the party was hit')
 f.env.OnRunScript('k_def_death01',2); assert(f.locals[7]==3,'a corpse who left the party did not detonate')
 f.env.OnRunScript('k_def_death01',21); assert(f.locals[7]==3,'a corpse who joined the party detonated')
 flags(f,{[2]=0,[5]=0})
end)
test(CHAIN,'tags decide nothing: a hostile with a companion tag is hit, a member with a hostile tag and an untagged hostile are judged by membership',function(F,p)
 local f=watch(F.new(p):load())
 f.objects[22]={tag='bastila',x=4}; f.objects[3]={tag='sith',party=1,x=2,min_one_hp=0}; f.objects[23]={tag='',x=5}
 f.party={1,2,3}; f.area_objects={20,22,3,23,2,1}; f:arm()
 f.env.OnRunScript('k_def_death01',20)
 assert(f.damaged[22]==1 and f.damaged[23]==1 and not f.damaged[3] and not f.damaged[2])
 flags(f,{[3]=0})
end)
test(CHAIN,'a death during a module transition does nothing; the next armed death blasts again with the party still left out',function(F,p)
 local f=watch(F.new(p):load()); f.area_objects={20,21,2,1}; f:arm()
 f.env.OnRunScript('k_def_death01',20); assert(f.damaged[21]==1)
 f.env.OnModuleLoad(); local calls=f:count('EffectDamage')
 f.objects[22]={tag='sith3',x=2}; f.area_objects={22,21,2,1}
 f.env.OnRunScript('k_def_death01',22); f.env.OnRunScript('k_def_death01',2)
 assert(f:count('EffectDamage')==calls and f.locals[7]==1,'a blast went off while disarmed')
 f:arm(); f.env.OnRunScript('k_def_death01',22)
 assert(f.locals[7]==2 and f.damaged[21]==2 and not f.damaged[2] and not f.damaged[1])
 flags(f,{})
end)
test(CHAIN,'unload mid-chain leaves nothing to put back',function(F,p)
 local f=watch(F.new(p):load()); f.objects[1].min_one_hp=0; f.objects[2].min_one_hp=1
 f.area_objects={20,21,2,1}; f:arm()
 f.env.OnRunScript('k_def_death01',20)
 local before=#f.calls
 if f.env.OnScriptUnload then f.env.OnScriptUnload(true) end
 for i=before+1,#f.calls do local c=f.calls[i]; assert(c.args[1]~=1 and c.args[1]~=2,'unload touched the party: '..c.name) end
 assert(#f.timers==0,'a timer outlives the blast')
 flags(f,{[1]=0,[2]=1})
end)
test(CHAIN,'OnAreaEnter takes from_save_game: an in-module enter disarms and keeps the detonated set; a save-game enter empties it',function(F,p)
 local f=watch(F.new(p):load()); f.area_objects={20,21,2,1}; f:arm()
 f.env.OnRunScript('k_def_death01',20); assert(f.locals[7]==1)
 f.env.OnAreaEnter(99,77,0,true); assert(f.locals[5]==0,'area enter did not disarm')
 rearm_in_module(f); f.env.OnRunScript('k_def_death01',20)
 assert(f.locals[7]==1,'from_save_game=0 emptied the detonated set (0 is true in Lua)')
 f.env.OnAreaEnter(99,1,1,true); rearm_in_module(f); f.env.OnRunScript('k_def_death01',20)
 assert(f.locals[7]==2,'a save-game enter kept the old detonated set')
 flags(f,{})
end)
test(CHAIN,'party answers: an error or an unknown answer keeps a creature out and stops its detonation; a false answer means not in the party',function(F,p)
 local f=watch(F.new(p):load()); f.area_objects={20,21,22,2,1}; f.objects[22]={tag='sith3',x=4}; f:arm()
 local real=function(id) return f.objects[id] and f.objects[id].party or 0 end
 f.overrides.IsObjectPartyMember=function(id) if id==21 then error('bridge refused') end if id==22 then return 'odd' end return real(id) end
 f.env.OnRunScript('k_def_death01',20)
 assert(f.locals[7]==1 and not f.damaged[21] and not f.damaged[22] and not f.damaged[2])
 f.env.OnRunScript('k_def_death01',21); assert(f.locals[7]==1,'a corpse with no party answer detonated')
 f.overrides.IsObjectPartyMember=function(id) if f.objects[id] and f.objects[id].party==1 then return true end return false end
 f.objects[23]={tag='sith4',x=4}; f.area_objects={23,21,2,1}
 f.env.OnRunScript('k_def_death01',23)
 assert(f.locals[7]==2 and f.damaged[21]==1 and not f.damaged[2] and not f.damaged[1],'a boolean false answer was not read as "not in the party"')
 flags(f,{})
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
