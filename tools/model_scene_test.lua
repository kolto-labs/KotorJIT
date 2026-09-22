-- Actual authored demos under fresh controlled APIs, not text/source assertions.
local root=assert(arg[1])
local function run(filename,mode)
  local ids={[10]={base=1.2,effective=1.8,valid=true,model="pc-model",creature="pc",server="server-pc"}}
  local locals={[5]=filename=="player_scale.lua" and 1 or 2,[6]=77,[7]=0,[8]=0,[9]=0}
  local logs,requests={},{};local counter=10;local mutations=0;local restores=0;local mismatch=false;local warming=false;local module="arena";local area=30;local destroyed=0;local tick=0;local location_index=0
  local env=setmetatable({}, {__index=_G})
  local function identity(id)
    local s=ids[id];if not s or not s.valid or mode=="noidentity" then return nil,"identity unavailable" end
    return {id=id,server=s.server}
  end
  local function matches(owner)
    local s=ids[owner.id];if not s or not s.valid or s.server~=owner.server then return nil,"stale server identity" end
    return true
  end
  local function snap(id,owner)
    if owner then local ok,err=matches(owner);if not ok then return nil,err end end
    if (mode=="late_replacement" or mode=="legit_warmup") and id==11 and tick<5 then return nil,"warming model" end
    if (mode=="uncaptured" or mode=="warmuptimeout") and id~=10 or mode=="partialwarmup" and id==12 or mode=="missingfirst" and id==11 or mode=="missinglast" and id==13 then return nil,"warming model" end
    local state=ids[id];if not state or not state.valid then return nil,"absent" end
    local base=state.base
    if mode=="readback" and mismatch then base=99 end
    return {id=id,base=base,effective=state.effective,model=state.model,creature=state.creature}
  end
  env.kp={print=function(s)logs[#logs+1]=s end,model={
    capabilities=function()return {available=true}end,
    snapshot=snap,identify=identity,matches=matches,
    resize=function(c,scale)
      mutations=mutations+1
      if mode=="mutation" and mutations==2 then return nil,"setter failed" end
      local s=ids[c.id];local ratio=s.effective/s.base;s.base=scale;s.effective=ratio*scale
      if mode=="readback" then mismatch=true end
      return {base=s.base,effective=s.effective}
    end,
    restore=function(c)
      restores=restores+1
      if ids[c.id].model~=c.model then return nil,"identity changed" end
      if mode=="restore" then return nil,"restore failed" end
      local s=ids[c.id];s.base=c.base;s.effective=c.effective;mismatch=false
      return snap(c.id)
    end}}
  local routines={
    GetFirstPC=function()if warming then error("VM not bound")end;return 10 end,
    GetIsObjectValid=function(id)return ids[id] and ids[id].valid and 1 or 0 end,
    GetLocalNumber=function(id,i)assert(id==10);return locals[i] or 0 end,
    SetLocalNumber=function(id,i,value)assert(id==10);locals[i]=value end,
    GetIsInCombat=function(id)return mode=="combat" and id==11 and tick>=5 and tick<=10 and 1 or 0 end,GetIsInConversation=function()return 0 end,
    GetModuleFileName=function()return module end,GetArea=function()return area end,
    GetFacing=function()return 90 end,
    GetPosition=function()return {x=0,y=0,z=0}end,
    Location=function(p,facing)location_index=location_index+1;assert(math.abs(p.x-({2,0,-2})[location_index])<1e-6 and math.abs(p.y-6)<1e-6 and facing==270);return p end,
    CreateObject=function(kind,resref,loc,animation)
      assert(kind==1 and resref=="g_sithtroop01" and animation==0)
      if mode=="spawnfailure" and counter==11 then return 0x7f000000 end
      counter=counter+1;ids[counter]={base=1,effective=2,valid=true,model="model"..counter,creature="actor"..counter,server="server"..counter};return counter
    end,
    SetCommandable=function(value,id)assert(value==0 and id~=10);if mode=="setupfailure" then error("setup failed")end;ids[id].disabled=true end,
    ChangeToStandardFaction=function(id,faction)assert(faction==2);ids[id].faction=faction end,
    GetStandardFaction=function(id)return ids[id].faction end,
    DestroyObject=function(id,delay)assert(id~=10 and delay==0);assert(ids[id].base==1 or mode=="restore");destroyed=destroyed+1;ids[id].valid=false end,
  }
  env.nwscript={call=function(name,...)
    local f=assert(routines[name],"unexpected NW routine "..name);requests[#requests+1]=name;return f(...)
  end}
  env.dofile=function(path)local chunk=assert(loadfile(path));setfenv(chunk,env);return chunk()end
  env.dofile(root.."/"..filename)
  warming=true;for i=1,3 do env.OnTick()end;warming=false
  assert(#logs==0,"unbound startup permanently failed the scene")
  local expected=filename=="player_scale.lua" and 6 or 18
  for i=1,700 do
    tick=i
    if i==5 and mode=="late_replacement" then ids[11].model="replacement";ids[11].creature="replacement";ids[11].server="replacement" end
    if i==5 and mode=="context" then module="other";area=31 end
    if i==5 and mode=="replaced" then for id,state in pairs(ids)do if id~=10 then state.model="replacement";state.creature="replacement" end end end
    env.OnTick()
    if (mode=="uncaptured" or mode=="partialwarmup" or mode=="missingfirst" or mode=="missinglast") and i==5 then
      for id,state in pairs(ids)do if id~=10 then state.model="replacement";state.creature="replacement";state.server="replacement" end end
      env.OnScriptUnload();assert(destroyed==0,"deleted replacement without retained identity");break
    end
    if mode=="unload" and i==5 then env.OnScriptUnload();break end
  end
  local complete,phases=0,0
  for _,line in ipairs(logs) do
    if line:find("complete phases=",1,true)then complete=complete+1;assert(line:find("phases=6",1,true))end
    if line:find("phase=",1,true)then phases=phases+1 end
  end
  if not mode or mode=="legit_warmup" then
    assert(complete==1 and phases==expected and locals[7]==1 and locals[8]==0)
    assert(mutations==expected)
    local old=mutations;env.OnTick();assert(mutations==old,"completed scene repeated")
  else assert(complete==0 and locals[7]==0,"partial/error scene published completion") end
  if mode~="restore" and mode~="context" then assert(ids[10].base==1.2 and math.abs(ids[10].effective-1.8)<1e-6) end
  if filename=="npc_wave.lua" then for id,state in pairs(ids)do if id~=10 then
    if mode=="context" or mode=="replaced" or mode=="uncaptured" or mode=="partialwarmup" or mode=="missingfirst" or mode=="missinglast" or mode=="noidentity" or mode=="late_replacement" and id==11 then assert(state.valid,"deleted replacement/context actor")
    else assert(not state.valid);if mode~="setupfailure" then assert(state.disabled and state.faction==2)end end
  end end end
  if mode~="context" and mode~="uncaptured" and mode~="warmuptimeout" and mode~="spawnfailure" and mode~="setupfailure" and mode~="noidentity" then assert(restores>0) end
  if mode=="partialwarmup" or mode=="missingfirst" or mode=="missinglast" then assert(restores==2,"discarded partial model captures") end
  if mode=="late_replacement" then assert(mutations==0 and ids[11].valid,"replacement was scaled or deleted") end
  if not mode then env.OnScriptUnload();assert(locals[6]==77)end
end
if arg[2] then run("npc_wave.lua",arg[2]);print("targeted scene case passed: "..arg[2]);return end
for _,file in ipairs{"player_scale.lua","npc_wave.lua"} do
 for _,mode in ipairs{false,"mutation","readback","restore","unload"}do run(file,mode or nil)end
end
run("npc_wave.lua","context");run("npc_wave.lua","replaced")
run("npc_wave.lua","uncaptured");run("npc_wave.lua","partialwarmup");run("npc_wave.lua","warmuptimeout")
run("npc_wave.lua","combat")
for _,mode in ipairs{"missingfirst","missinglast","spawnfailure","setupfailure"}do run("npc_wave.lua",mode)end
run("npc_wave.lua","late_replacement");run("npc_wave.lua","legit_warmup");run("npc_wave.lua","noidentity")
print("23 actual demo lifecycle/phase/failure/cleanup cases passed")
