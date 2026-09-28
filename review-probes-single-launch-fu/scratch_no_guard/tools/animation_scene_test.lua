-- Execute the actual scene; clocks advance outside its API calls.
local path=assert(arg[1])
local function run(mode)
 local env=setmetatable({}, {__index=_G})
 local locals={[5]=8,[6]=77};local actors={};local nextid=10;local module="arena";local area=1
 local tick=0;local calls,logs={},{};local deletes=0;local oldhold=nil;local holdframes=0
 local function matches(o)local a=actors[o.id];return a and a.valid and a.owner==o.owner or nil,"stale ownership"end
 local function snapshot(id,o)
  if o and not matches(o)then return nil,"stale"end
  if (mode=="warmup" or mode=="late_replace") and tick<5 then return nil,"warming"end
  local a=actors[id];if not a or not a.valid then return nil,"missing"end
  return {id=id,model=a.model,creature=a.owner}
 end
 local function inspect(c,clip)
  local a=actors[c.id];if not a or not a.valid or c.model~=a.model then return nil,"stale capture"end
  if mode=="absent" and clip=="dance"then return {available=false,active=false,time=-1,duration=-1}end
  return {available=true,active=a.clip==clip,time=a.clip==clip and a.time or -1,duration=2.06667,units="seconds"}
 end
 env.kp={print=function(s)logs[#logs+1]=s end,model={
  identify=function(id)if mode=="noidentity"then return nil,"unavailable"end;return {id=id,owner=actors[id].owner}end,
  matches=matches,snapshot=snapshot},animation={capabilities=function()return {available=true}end,inspect=inspect,
  cue=function(c,clip,rate,start)
   calls[#calls+1]={id=c.id,clip=clip,rate=rate,start=start}
   if mode=="cuefailure" and clip=="dance"then return nil,"cue failed"end
   local a=actors[c.id];assert(a.model==c.model)
   if a.clip~=clip then a.time=start or 0 end
   a.clip=clip;a.rate=mode=="pauseignored" and rate==0 and 0.5 or rate
   return inspect(c,clip)
  end}}
 local routines={GetFirstPC=function()return 1 end,
  GetIsObjectValid=function(id)return id==1 or actors[id] and actors[id].valid and 1 or 0 end,
  GetLocalNumber=function(_,i)return locals[i] or 0 end,SetLocalNumber=function(_,i,v)locals[i]=v end,
  GetModuleFileName=function()return module end,GetArea=function()return area end,
  GetIsInCombat=function(id)return mode=="combat" and id==11 and tick==6 and 1 or 0 end,
  GetIsInConversation=function()return 0 end,GetIsDead=function()return 0 end,
  GetPosition=function()return {x=0,y=0,z=0}end,GetFacing=function()return 0 end,
  Location=function(p,f)assert(p.x==6 and math.abs(p.y)==1.5 and f==180);return p end,
  CreateObject=function(kind,resref)
   assert(kind==1 and resref=="g_sithtroop01")
   if mode=="partial" and nextid==11 then return 0 end
   nextid=nextid+1;actors[nextid]={valid=true,owner=nextid,model=nextid,time=0,rate=1};return nextid
  end,
  SetCommandable=function(v,id)assert(v==0 and actors[id])end,
  ChangeToStandardFaction=function(id,v)assert(v==2);actors[id].faction=v end,
  GetStandardFaction=function(id)return actors[id].faction end,
  DestroyObject=function(id)assert(actors[id]);deletes=deletes+1;if mode~="deletefailure"then actors[id].valid=false end end}
 env.nwscript={call=function(name,...)return assert(routines[name],"unexpected NW routine "..name)(...)end}
 local chunk=assert(loadfile(path));setfenv(chunk,env);chunk()
 for i=1,1000 do
  tick=i
  for _,a in pairs(actors)do
   if a.valid and a.clip then a.time=math.min(2.06667,a.time+a.rate/60)end
  end
  if tick==5 and mode=="late_replace"then actors[11].owner=99;actors[11].model=99 end
  if tick==6 and mode=="context"then module="elsewhere";area=2 end
  if tick==6 and mode=="modelreplace"then actors[11].model=99 end
  if locals[6]==4 and mode=="override"then actors[11].clip="pause1"end
  if mode=="stalled"then for _,a in pairs(actors)do a.rate=0 end end
  env.OnTick()
  if locals[6]==4 and locals[8]==0 then
   holdframes=holdframes+1
   local a=actors[11]
   if oldhold then assert(math.abs(a.time-oldhold)<0.002)end
   oldhold=a.time
  end
  if mode=="unload" and tick==6 then env.OnScriptUnload();break end
 end
 local success=not mode or mode=="warmup"
 assert((locals[7]==1)==success,"unexpected completion "..tostring(mode))
 if success then
  assert(deletes==2 and holdframes>60,"missing sustained hold/cleanup")
  assert(#calls==8,"cue repeated or baseline omitted")
  assert(calls[5].id==11 and calls[5].rate==0 and calls[5].start==nil)
  assert(calls[6].id==11 and calls[6].rate==0.5 and calls[6].start==nil)
  env.OnTick();assert(#calls==8);env.OnScriptUnload();assert(locals[6]==77)
 elseif mode=="context"then assert(deletes==0)
 elseif mode=="late_replace" or mode=="modelreplace"then assert(actors[11].valid,"deleted replacement")
 elseif mode=="noidentity"then assert(deletes==0)
 elseif mode~="deletefailure"then for _,a in pairs(actors)do assert(not a.valid,"owned actor leaked "..tostring(mode))end end
 if not success and mode~="unload" and mode~="context"then assert(locals[8]==1,"failure not reported")end
end
for _,mode in ipairs{false,"warmup","late_replace","modelreplace","context","combat","partial","noidentity","absent","cuefailure","pauseignored","override","stalled","deletefailure","unload"}do run(mode or nil)end
print("15 actual animation scene clock/lifecycle/failure cases passed; controlled backend only")
