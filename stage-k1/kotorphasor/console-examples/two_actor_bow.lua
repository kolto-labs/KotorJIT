-- Two disposable actors, one native clock held while the other continues.
-- Trigger PC local5=8. Local6: phase,7:complete,8:failed,9:owned count.
-- Camera/framing belongs to the recording driver, not this scene.
priority=30
local q=function(name,...) return nwscript.call(name,...) end
local checked=function(value,err) assert(value,err or "native animation operation failed");return value end
local yes=function(v)return v==1 or v==true end
local actors,owners,captures,originals={},{},{},{}
local state="waiting"
local pc,context,held,lastA,lastB
local elapsed,total=0,0
local function log(s)kp.print("[animation-scene:freeze] "..s)end
local function valid(id)return id and yes(q("GetIsObjectValid",id))end
local function context_ok()return context and q("GetModuleFileName")==context.module and q("GetArea",pc)==context.area end
local function number(i,v)assert(context_ok(),"context changed; refusing local write");q("SetLocalNumber",pc,i,v)end
local function same(id)
 checked(kp.model.matches(assert(owners[id],"missing initial ownership")))
 if captures[id] then
  local fresh=checked(kp.model.snapshot(id,owners[id]))
  assert(fresh.model==captures[id].model and fresh.creature==captures[id].creature,"model identity changed")
 end
end
local function cleanup()
 assert(context_ok(),"context changed; refusing deletion")
 local errors={}
 for _,id in ipairs(actors)do
  if valid(id)then
   local ok,err=pcall(function()
    assert(q("GetArea",id)==context.area,"actor left area")
    same(id)
    q("DestroyObject",id,0)
   end)
   if not ok then errors[#errors+1]=tostring(err)end
  end
 end
 assert(#errors==0,table.concat(errors,"; "))
end
local function phase(s,n)state=s;elapsed=0;number(6,n);log("phase="..n.." "..s)end
local function inspect(i,clip)
 local s=checked(kp.animation.inspect(captures[actors[i]],clip or "bow"))
 assert(s.available and s.duration>0,"required clip unavailable")
 return s
end
local function cue(i,clip,rate,start)return checked(kp.animation.cue(captures[actors[i]],clip,rate,start))end
local function active(i)local s=inspect(i);assert(s.active,"controller replaced dance run");return s end
function OnTick()
 if state=="complete" or state=="failed" then return end
 local ok,err=pcall(function()
  if state=="waiting" then
   local ready,p=pcall(q,"GetFirstPC")
   if not ready or not valid(p)then return end
   local readable,trigger=pcall(q,"GetLocalNumber",p,5)
   if not readable or trigger~=8 then return end
   pc=p;context={module=q("GetModuleFileName"),area=q("GetArea",pc)}
   assert(kp.animation.capabilities().available,"native animation backend unavailable")
   assert(not yes(q("GetIsInCombat",pc)) and not yes(q("GetIsInConversation",pc)),"peaceful gameplay required")
   for i=6,9 do originals[i]=q("GetLocalNumber",pc,i);number(i,0)end
   number(5,0)
   local p=q("GetPosition",pc);local facing=q("GetFacing",pc);local a=math.rad(facing)
   for _,side in ipairs{-1.5,1.5}do
    local loc=q("Location",{x=p.x+6*math.cos(a)-side*math.sin(a),y=p.y+6*math.sin(a)+side*math.cos(a),z=p.z},(facing+180)%360)
    local id=q("CreateObject",1,"g_sithtroop01",loc,0)
    assert(valid(id),"spawn failed");actors[#actors+1]=id
    owners[id]=checked(kp.model.identify(id))
    q("SetCommandable",0,id);q("ChangeToStandardFaction",id,2)
    assert(q("GetStandardFaction",id)==2,"friendly faction readback failed")
   end
   number(9,2);phase("models",1)
  end
  total=total+1;elapsed=elapsed+1;assert(total<900,"scene deadline")
  assert(context_ok(),"scene context changed")
  assert(valid(pc) and not yes(q("GetIsInCombat",pc)) and not yes(q("GetIsInConversation",pc)),"player no longer peaceful")
  for _,id in ipairs(actors)do
   if valid(id)then
    assert(q("GetArea",id)==context.area,"actor left area");same(id)
    assert(not yes(q("GetIsInCombat",id)) and not yes(q("GetIsDead",id)),"owned actor no longer peaceful/alive")
   else assert(state=="cleanup","actor disappeared")end
  end
  if state=="models" then
   local ready=true
   for _,id in ipairs(actors)do
    if not captures[id]then captures[id]=kp.model.snapshot(id,owners[id])end
    if not captures[id]then ready=false end
   end
   if not ready then assert(elapsed<180,"model readiness deadline");return end
   for i=1,2 do inspect(i,"pause1");inspect(i);cue(i,"pause1",1)end
   phase("baseline",2)
  elseif state=="baseline" then
   for i=1,2 do assert(inspect(i,"pause1").active,"baseline overridden")end
   if elapsed>=90 then
    local a=cue(1,"bow",0.5,0);local b=cue(2,"bow",0.5,0)
    assert(math.abs(a.duration-b.duration)<0.001,"actors have different clip duration")
    lastA=a.time;lastB=b.time;phase("advance",3)
   end
  elseif state=="advance" then
   local a,b=active(1),active(2)
   assert(a.time>=lastA-0.001 and b.time>=lastB-0.001,"clip clock restarted")
   lastA,lastB=a.time,b.time
   if a.time>=a.duration*0.33 then held=cue(1,"bow",0).time;phase("hold",4)end
  elseif state=="hold" then
   local a,b=active(1),active(2)
   assert(math.abs(a.time-held)<0.002,"pause did not hold native clock")
   assert(b.time>=lastB-0.001,"comparison clock restarted");lastB=b.time
   if b.time>=b.duration*0.80 then cue(1,"bow",0.5);lastA=a.time;phase("resume",5)end
  elseif state=="resume" then
   local a,b=active(1),active(2)
   assert(a.time>=lastA-0.001 and b.time>=lastB-0.001,"resumed/comparison clock restarted")
   lastA,lastB=a.time,b.time
   if a.time>=held+a.duration*0.12 then
    for i=1,2 do cue(i,"pause1",1)end
    phase("reset-baseline",6)
   end
  elseif state=="reset-baseline" then
   for i=1,2 do assert(inspect(i,"pause1").active,"baseline reset overridden")end
   if elapsed>=90 then cleanup();phase("cleanup",7)end
  elseif state=="cleanup" then
   for _,id in ipairs(actors)do if valid(id)then assert(elapsed<180,"cleanup deadline");return end end
   number(7,1);state="complete";log("complete owned=2 baseline=pause1")
  end
 end)
 if not ok then
  state="failed";local clean,why=pcall(cleanup);pcall(number,8,1)
  log("failed="..tostring(err).." cleanup="..tostring(clean)..(clean and "" or " "..tostring(why)))
 end
end
function OnScriptUnload()
 if pc then
  local ok,err=pcall(function()
   if state~="complete"then cleanup()end
   for i,v in pairs(originals)do number(i,v)end
  end)
  if not ok then log("unload cleanup failed="..tostring(err))end
 end
end
