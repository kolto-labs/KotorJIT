-- Controlled Lua boundary only: requests and decisions, never engine effects.
local F = { INVALID = 2130706432, instances={} }
function F.source(path)
  local source = assert(F.sources and F.sources[path], 'unmapped example: '..path)
  return source
end
function F.new(path, overrides)
  local f = {calls={}, prints={}, timers={}, locals={}, objects={
    [1]={tag='pc',party=1,x=0,appearance=136}, [2]={tag='bastila',party=1,x=1,appearance=7},
    [20]={tag='sith',x=3,appearance=28}, [21]={tag='sith2',x=5,appearance=29}, [30]={tag='metalbox',x=2},
    [40]={tag='medpac',x=0}}, party={1,2}, area_objects={20,21,2}, hp=100,
    module='danm13', second=10, speed=1, now=0, overrides=overrides or {}}
  F.instances[#F.instances+1]=f; f.unexpected={}
  local iter, inventory, next_effect, next_token = 0, 0, 1, 1000
  f.effects, f.effect_lists, f.effect_iter = {}, {}, {}
  local function obj(id) return f.objects[id] or {} end
  -- Match the native bridge boundary: every effect enumeration materializes a
  -- fresh wrapper. It is valid for inspection/removal but has no Lua-stable
  -- identity across independent enumerations.
  local function effect_ref(handle)
    local effect=f.effects[handle]
    return handle and {handle=handle,token_id=effect and effect.token_id} or 0
  end
  local function effect_handle(value) return type(value)=='table' and value.handle or value end
  local function refresh_appearance(id)
    local appearance = obj(id).appearance
    for _, handle in ipairs(f.effect_lists[id] or {}) do
      local effect = f.effects[handle]
      if effect and effect.active and effect.name == 'EffectDisguise' then
        appearance = effect.args[1]
      end
    end
    obj(id).current_appearance = appearance
  end
  local function add_effect(id, effect, duration, seconds)
    if not f.objects[id] or type(effect) ~= 'table' then return end
    local handle = next_effect; next_effect = next_effect + 1
    local expires_at = duration == 1 and type(seconds) == 'number' and seconds > 0
      and f.now + math.ceil(seconds * 60) or nil
    f.effects[handle] = {active=true,name=effect.effect,args=effect.args,token_id=effect.token_id,expires_at=expires_at}
    f.effect_lists[id] = f.effect_lists[id] or {}
    f.effect_lists[id][#f.effect_lists[id]+1] = handle
    refresh_appearance(id)
  end
  local function expire_effects()
    for id, list in pairs(f.effect_lists) do
      local changed=false
      for _, handle in ipairs(list) do
        local effect=f.effects[handle]
        if effect and effect.active and effect.expires_at and effect.expires_at <= f.now then effect.active=false; changed=true end
      end
      if changed then refresh_appearance(id) end
    end
  end
  f.apply_effect=add_effect
  f.expire_effects=expire_effects
  local r = {
    GetFirstPC=function() return 1 end, GetModuleName=function() return f.module end,
    GetArea=function() return 99 end, GetObjectByTag=function(tag) for id,o in pairs(f.objects) do if o.tag==tag then return id end end return F.INVALID end,
    GetIsObjectValid=function(id) return f.objects[id] and 1 or 0 end,
    IsObjectPartyMember=function(id) return obj(id).party or 0 end,
    GetIsDead=function(id) return obj(id).dead or 0 end,
    GetPartyMemberCount=function() return #f.party end, GetPartyMemberByIndex=function(i) return f.party[i+1] or F.INVALID end,
    GetTag=function(id) return obj(id).tag or '' end, GetName=function(id) return obj(id).tag or '' end,
    GetPosition=function(id) return {x=obj(id).x or 0,y=0,z=0} end,
    GetDistanceBetween=function(a,b) return math.abs((obj(a).x or 0)-(obj(b).x or 0)) end,
    GetCurrentHitPoints=function() return f.hp end, GetMaxHitPoints=function() return 100 end,
    GetFirstObjectInArea=function() iter=1 return f.area_objects[iter] or F.INVALID end,
    GetNextObjectInArea=function() iter=iter+1 return f.area_objects[iter] or F.INVALID end,
    GetFirstItemInInventory=function(id) inventory=1 return id==30 and 40 or F.INVALID end,
    GetNextItemInInventory=function() inventory=inventory+1 return F.INVALID end,
    GetItemInSlot=function() return F.INVALID end,
    GetFirstEffect=function(id)
      local list=f.effect_lists[id] or {}; local n=1
      while list[n] and not (f.effects[list[n]] and f.effects[list[n]].active) do n=n+1 end
      f.effect_iter[id]=n; return effect_ref(list[n])
    end,
    GetNextEffect=function(id)
      local list=f.effect_lists[id] or {}; local n=(f.effect_iter[id] or 1)+1
      while list[n] and not (f.effects[list[n]] and f.effects[list[n]].active) do n=n+1 end
      f.effect_iter[id]=n; return effect_ref(list[n])
    end,
    GetIsEffectValid=function(value) local handle=effect_handle(value); return f.effects[handle] and f.effects[handle].active and 1 or 0 end,
    GetEffectType=function(value) local effect=f.effects[effect_handle(value)]; return effect and effect.name or nil end,
    RemoveEffect=function(id,value)
      local handle=effect_handle(value); local token=type(value)=='table' and value.token_id or nil
      local effect=f.effects[handle]
      if not effect and token then
        for _, candidate in ipairs(f.effect_lists[id] or {}) do
          if f.effects[candidate] and f.effects[candidate].token_id==token then effect=f.effects[candidate]; break end
        end
      end
      if effect then effect.active=false; refresh_appearance(id) end
    end,
    GetIsEnemy=function(id) return obj(id).party and 0 or 1 end,
    GetTimeSecond=function() return f.second end, GetFacing=function() return 90 end, GetLocation=function() return {position={x=0,y=0,z=0}} end,
    GetLastAttacker=function() return 1 end, GetLastPerceived=function() return 1 end,
    GetLastSpeaker=function() return 2 end, GetPCSpeaker=function() return 1 end,
    GetAppearanceType=function(id) return obj(id).current_appearance or obj(id).appearance end, GetItemPossessor=function() return 1 end,
    GetGoodEvilValue=function() return f.alignment or 50 end,
    Location=function(p,face) return {position=p,facing=face} end,
    Vector=function(x,y,z) return {x=x,y=y,z=z} end,
    CreateObject=function() f.objects[100]={tag='created'} return 100 end,
    EventUserDefined=function(n) return {event=n} end,
    SetLocalNumber=function(id,slot,n) f.locals[slot]=n end,
    ApplyEffectToObject=function(duration,effect,id,seconds) add_effect(id,effect,duration,seconds) end,
    GetMinOneHP=function(id) return obj(id).min_one_hp or 0 end,
    SetMinOneHP=function(id,n) if f.objects[id] then f.objects[id].min_one_hp=n end end,
  }
  for _,name in ipairs({'GetCurrentAction','GetIsConversationActive','GetIsInConversation','GetGlobalNumber','GetGlobalBoolean','GetIsOpen','GetLocked','GetLockKeyRequired','GetPlotFlag','GetIsDoorActionPossible','GetCommandable'}) do r[name]=function() return 0 end end
  r.GetIsInCombat=function(id) return obj(id).combat or 0 end
  local voids={}
  for name in ('SpeakString SetGlobalFadeOut SetGlobalFadeIn SetGlobalBoolean SetGlobalNumber StartNewModule DoSinglePlayerAutoSave ClearAllActions ActionStartConversation JumpToObject ActionMoveToObject ActionMoveToLocation ActionAttack ActionOpenDoor ActionTakeItem SignalEvent ExecuteScript DestroyObject ChangeToStandardFaction SetMinOneHP MusicBattlePlay ActionPlayAnimation JumpToLocation'):gmatch('%S+') do voids[name]=true end
  local effects={}
  for name in ('EffectWhirlWind EffectHorrified EffectHaste EffectDamageShield EffectAttackIncrease EffectDisguise EffectVisualEffect EffectForcePushed EffectDamage EffectDeath EffectForceWhirlwind EffectChoke EffectFear EffectSpeedIncrease EffectHeal EffectBeam EffectStunned EffectParalyze EffectKnockdown EffectInvisibility EffectMovementSpeedIncrease'):gmatch('%S+') do effects[name]=true end
  f.env=setmetatable({math=setmetatable({random=function() return f.random or 1 end},{__index=math})},{__index=_G})
  f.env.kp={registertimer=function(ms,name,data) f.timers[#f.timers+1]={ms=ms,name=name,data=data}; return #f.timers end, print=function(s) f.prints[#f.prints+1]=s end, diagnostic=function() end,
    game_speed=function(n) if n then f.speed=n end return f.speed end,
    speed=function(n) return math.max(1,math.min(16,n)) end}
  f.env.nwscript={call=function(name,...)
    local c={name=name,args={...},caller=f.caller}; f.calls[#f.calls+1]=c
    local fn=f.overrides[name] or r[name]
    if fn then return fn(...) end
    if voids[name] then return end -- actual bridge Type::Void has zero results
    if effects[name] then local token={effect=name,args={...},token_id=next_token}; next_token=next_token+1; return token end
    f.unexpected[#f.unexpected+1]=name
    error('Undeclared fixture routine: '..name)
  end, with_caller=function(id,fn,...)
    local previous=f.caller; f.caller=id
    local results={pcall(fn,...)}; f.caller=previous
    if not results[1] then error(results[2]) end
    return unpack(results,2)
  end}
  function f:load(source)
    local chunk=source and assert(loadstring(source,path)) or assert(loadfile(F.source(path)))
    setfenv(chunk,self.env); self.result=chunk(); return self
  end
  function f:count(name) local n=0 for _,c in ipairs(self.calls) do if c.name==name then n=n+1 end end return n end
  function f:last(name) for i=#self.calls,1,-1 do if self.calls[i].name==name then return self.calls[i] end end end
  function f:has(text) for _,s in ipairs(self.prints) do if s:find(text,1,true) then return true end end return false end
  function f:appearance(id) return self.env.nwscript.call('GetAppearanceType',id) end
  function f:active_effects(id)
    local n=0
    for _, handle in ipairs(self.effect_lists[id] or {}) do if self.effects[handle] and self.effects[handle].active then n=n+1 end end
    return n
  end
  function f:active_disguises(id)
    local n=0
    for _, handle in ipairs(self.effect_lists[id] or {}) do
      local effect=self.effects[handle]
      if effect and effect.active and effect.name=='EffectDisguise' then n=n+1 end
    end
    return n
  end
  function f:tick(tick) self.now=tick; self:expire_effects(); return self.env.OnTick(tick,true) end
  function f:fire(i) local t=assert(self.timers[i]); return self.env[t.name](i,1,t.data) end
  function f:arm() self.env.OnModuleLoad(); assert(self.locals[5]==0); for i=1,199 do self.env.OnTick(i,true) end assert(self.locals[5]==0); self.env.OnTick(200,true); assert(self.locals[5]==1) end
  return f
end
return F
