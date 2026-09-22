-- Actual authored demos under fresh controlled APIs, not text/source assertions.
local root=assert(arg[1])
local function run(filename,mode)
  local ids={[10]={base=1.2,effective=1.8,valid=true,model="pc-model",creature="pc"}}
  local locals={[5]=filename=="player_scale.lua" and 1 or 2,[6]=77,[7]=0,[8]=0,[9]=0}
  local logs,requests={},{};local counter=10;local mutations=0;local restores=0;local mismatch=false;local warming=false;local module="arena";local area=30;local destroyed=0
  local env=setmetatable({}, {__index=_G})
  local function snap(id)
    local state=ids[id];if not state or not state.valid then return nil,"absent" end
    local base=state.base
    if mode=="readback" and mismatch then base=99 end
    return {id=id,base=base,effective=state.effective,model=state.model,creature=state.creature}
  end
  env.kp={print=function(s)logs[#logs+1]=s end,model={
    capabilities=function()return {available=true}end,
    snapshot=snap,
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
    GetIsInCombat=function()return 0 end,GetIsInConversation=function()return 0 end,
    GetModuleFileName=function()return module end,GetArea=function()return area end,
    GetFacing=function()return 90 end,
    GetPosition=function()return {x=0,y=0,z=0}end,
    Location=function(p,facing)assert(math.abs(p.x)>2.9 and math.abs(p.y-3)<1e-6 and facing==270);return p end,
    CreateObject=function(kind,resref,loc,animation)
      assert(kind==1 and resref=="g_sithtroop01" and animation==0)
      counter=counter+1;ids[counter]={base=1,effective=2,valid=true,model="model"..counter,creature="actor"..counter};return counter
    end,
    SetCommandable=function(value,id)assert(value==0 and id~=10);ids[id].disabled=true end,
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
    if i==5 and mode=="context" then module="other";area=31 end
    if i==5 and mode=="replaced" then for id,state in pairs(ids)do if id~=10 then state.model="replacement";state.creature="replacement" end end end
    env.OnTick()
    if mode=="unload" and i==5 then env.OnScriptUnload();break end
  end
  local complete,phases=0,0
  for _,line in ipairs(logs) do
    if line:find("complete phases=",1,true)then complete=complete+1;assert(line:find("phases=6",1,true))end
    if line:find("phase=",1,true)then phases=phases+1 end
  end
  if not mode then
    assert(complete==1 and phases==expected and locals[7]==1 and locals[8]==0)
    assert(mutations==expected)
    local old=mutations;env.OnTick();assert(mutations==old,"completed scene repeated")
  else assert(complete==0 and locals[7]==0,"partial/error scene published completion") end
  if mode~="restore" and mode~="context" then assert(ids[10].base==1.2 and math.abs(ids[10].effective-1.8)<1e-6) end
  if filename=="npc_wave.lua" then for id,state in pairs(ids)do if id~=10 then
    if mode=="context" or mode=="replaced" then assert(state.valid and destroyed==0,"deleted replacement/context actor")
    else assert(not state.valid and state.disabled and state.faction==2) end
  end end end
  if mode~="context" then assert(restores>0) end
  if not mode then env.OnScriptUnload();assert(locals[6]==77)end
end
for _,file in ipairs{"player_scale.lua","npc_wave.lua"} do
 for _,mode in ipairs{false,"mutation","readback","restore","unload"}do run(file,mode or nil)end
end
run("npc_wave.lua","context");run("npc_wave.lua","replaced")
print("12 actual demo lifecycle/phase/failure/cleanup cases passed")
