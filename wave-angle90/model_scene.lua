-- Shared finite scale choreography. Load through the two authored scene files.
-- No offsets/ABI knowledge here: native kp.model owns checked memory operations.
local M = {}
local function yes(v) return v == 1 or v == true end
local function close(a, b) return math.abs(a-b) <= 0.001 * math.max(1, math.abs(b)) end
local function call(name, ...) return nwscript.call(name, ...) end
local function checked(value, error) assert(value, error or "native model operation failed"); return value end

function M.new(config)
  local self = {state="waiting", phase=0, elapsed=0, actors={}, captures={}, capture_by_id={}, ownership={}, originals={}, pc=nil, context=nil}
  local function log(text) kp.print("[model-scene:"..config.name.."] "..text) end
  local function context_matches()
    return self.context and call("GetModuleFileName")==self.context.module
      and call("GetArea",self.pc)==self.context.area
  end
  local function number(index, value)
    assert(context_matches(),"scene context changed; refusing local write")
    call("SetLocalNumber", self.pc, index, value)
  end
  local function valid(id) return id and yes(call("GetIsObjectValid", id)) end
  local function read(capture, base)
    local current = checked(kp.model.snapshot(capture.id,self.ownership[capture.id]))
    assert(current.model == capture.model and current.creature == capture.creature, "scene actor identity changed")
    assert(close(current.base, base), "independent base readback mismatch")
    assert(close(current.effective, capture.effective/capture.base*base), "independent effective readback mismatch")
    return current
  end
  local function restore(remove)
    assert(context_matches(),"scene context changed; refusing restore/deletion")
    local errors = {}
    for _, capture in ipairs(self.captures) do
      local ok, err = pcall(function() checked(kp.model.restore(capture)); read(capture,capture.base) end)
      if not ok then errors[#errors+1]=tostring(err) end
    end
    -- Remove only the actors this scene created. Restoring the PC never destroys it.
    for _, id in ipairs(self.actors) do
      if remove~=false and config.spawn and valid(id) then
        local ok, err = pcall(function()
          assert(call("GetArea",id)==self.context.area,"owned actor left scene area")
          local owner=self.ownership[id]
          assert(owner,"no initial actor ownership; refusing deletion")
          checked(kp.model.matches(owner))
          local capture=self.capture_by_id[id]
          if capture then
            local current=checked(kp.model.snapshot(id,owner))
            assert(current.model==capture.model and current.creature==capture.creature,
              "owned actor identity changed; refusing deletion")
          end
          call("DestroyObject",id,0)
        end)
        if not ok then errors[#errors+1]=tostring(err) end
      end
    end
    assert(#errors==0,table.concat(errors,"; "))
  end
  local function fail(err)
    self.state="failed"
    local restored, restore_error=pcall(restore)
    pcall(number,8,1)
    log("failed="..tostring(err).." cleanup="..tostring(restored)..(restored and "" or " "..tostring(restore_error)))
  end
  local function phase()
    self.phase=self.phase+1
    for i,capture in ipairs(self.captures) do
      local scale=config.scales[self.phase][(i-1)%#config.scales[self.phase]+1]
      checked(kp.model.resize(capture,scale))
      local current=read(capture,scale)
      log(("phase=%d actor=%d base=%.3f effective=%.3f"):format(self.phase,i,current.base,current.effective))
    end
    number(6,self.phase)
    self.elapsed=0
  end
  function self:tick()
    if self.state=="failed" or self.state=="complete" then return end
    local ok,err=pcall(function()
      if self.state=="waiting" then
        local ready,pc=pcall(call,"GetFirstPC")
        if not ready or not valid(pc) then return end
        local readable,trigger=pcall(call,"GetLocalNumber",pc,5)
        if not readable or trigger~=config.trigger then return end
        self.pc=pc
        self.context={module=call("GetModuleFileName"),area=call("GetArea",pc)}
        assert(kp.model.capabilities().available,"native model backend unavailable")
        assert(not yes(call("GetIsInCombat",pc)) and not yes(call("GetIsInConversation",pc)),"scene needs peaceful gameplay")
        for i=6,9 do self.originals[i]=call("GetLocalNumber",pc,i);number(i,0) end
        number(5,0)
        if config.spawn then
          local p=call("GetPosition",pc)
          local facing=call("GetFacing",pc)
          local angle=math.rad(facing+90)
          local fx,fy=math.cos(angle),math.sin(angle)
          for i=1,3 do
            local side=config.sides[i]
            local loc=call("Location",{x=p.x+config.forward*fx-side*fy,y=p.y+config.forward*fy+side*fx,z=p.z},(facing+180)%360)
            local id=call("CreateObject",1,config.resref,loc,0)
            assert(valid(id),"owned humanoid spawn failed")
            self.actors[#self.actors+1]=id
            self.ownership[id]=checked(kp.model.identify(id))
            call("SetCommandable",0,id)
            call("ChangeToStandardFaction",id,config.faction)
            assert(call("GetStandardFaction",id)==config.faction,"friendly faction readback failed")
            assert(not yes(call("GetIsInCombat",id)),"spawn entered combat")
          end
        else self.actors={pc} end
        number(9,#self.actors)
        log("setup actors="..#self.actors.." awaiting-models")
        self.state="models";self.elapsed=0
      end
      assert(context_matches(),"scene context changed")
      assert(valid(self.pc) and not yes(call("GetIsInCombat",self.pc))
        and not yes(call("GetIsInConversation",self.pc)),"gameplay actor lost, combat or conversation began")
      for _,id in ipairs(self.actors) do
        local exists=valid(id)
        assert(exists or self.state=="cleanup","scene actor disappeared")
        if exists then
          assert(call("GetArea",id)==self.context.area,"scene actor left area")
          if config.spawn then checked(kp.model.matches(assert(self.ownership[id],"missing initial ownership"))) end
          assert(not yes(call("GetIsInCombat",id)),"scene actor entered combat")
        end
      end
      if self.state=="models" then
        self.elapsed=self.elapsed+1
        local ready=true
        for _,id in ipairs(self.actors) do
          local capture=self.capture_by_id[id]
          if capture then read(capture,capture.base)
          else
            capture=kp.model.snapshot(id,self.ownership[id])
            if capture then
              self.capture_by_id[id]=capture
              self.captures[#self.captures+1]=capture
            else ready=false end
          end
        end
        if not ready then assert(self.elapsed<180,"model readiness deadline");return end
        -- Preserve authored actor order even when models became ready out of order.
        for i,id in ipairs(self.actors) do self.captures[i]=self.capture_by_id[id] end
        self.state="running";phase();return
      end
      self.elapsed=self.elapsed+1
      if self.state=="running" and self.elapsed>=config.hold_ticks then
        if self.phase<#config.scales then phase()
        else
          restore(false);self.state="restored";self.elapsed=0
          log("restored actors="..#self.captures.." holding-original-scale")
        end
      elseif self.state=="restored" and self.elapsed>=config.hold_ticks then
        restore();self.state="cleanup";self.elapsed=0
      elseif self.state=="cleanup" then
        if config.spawn then
          for _,id in ipairs(self.actors) do
            if valid(id) then assert(self.elapsed<180,"owned actor cleanup deadline");return end
          end
        else for _,c in ipairs(self.captures) do read(c,c.base) end end
        number(7,1);self.state="complete";log("complete phases="..self.phase.." restored="..#self.captures)
      end
    end)
    if not ok then fail(err) end
  end
  function self:unload()
    if self.pc then
      local ok,err=pcall(function()
        if self.state~="complete" then restore() end
        for index,value in pairs(self.originals) do number(index,value) end
      end)
      if not ok then log("unload cleanup failed="..tostring(err)) end
    end
  end
  return self
end
return M
