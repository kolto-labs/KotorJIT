-- Doppelganger: permanent disguises with exact constructor-token ownership.
-- K1 copies the constructor effect's immutable engine ID into the target;
-- RemoveEffect matches that ID. We retain each original constructor token and
-- never compare fresh wrappers returned by effect enumeration.
priority = 30

local MALAK = 21
local VFX_WHIRLWIND = 1018
local VFX_DARK_LIGHTNING = 2038
local DURATION_PERMANENT = 2
local DURATION_TEMPORARY = 1
local ARM_TICKS = 200
local SETTLE_TICKS = 40
local COUNTER_SLOT = 7

local function call(name, ...)
  if not nwscript or type(nwscript.call) ~= "function" then return false end
  return pcall(nwscript.call, name, ...)
end
local function q(name, ...)
  local ok, value = call(name, ...)
  return ok and value or nil
end
local function yes(value) return value == 1 or value == true end
local function row(value)
  return type(value) == "number" and value >= 0 and value == math.floor(value) and value or nil
end
local function valid_living(actor)
  return yes(q("GetIsObjectValid", actor)) and not yes(q("GetIsDead", actor))
end

local armed_flag, tick_count = false, 0
local original_pc_appearance, pc_state = nil, nil
local pending, copies, count = {}, {}, 0
local combat_seen, quiet_ticks, cleanup_required = false, 0, false
local restored, unavailable = 0, 0
local terminal_unavailable = {}

local function set_armed(value)
  armed_flag, tick_count = value, value and tick_count or 0
  local pc = q("GetFirstPC")
  if pc then q("SetLocalNumber", pc, 5, value and 1 or 0) end
end
local function clear_run()
  original_pc_appearance, pc_state = nil, nil
  pending, copies, count = {}, {}, 0
  combat_seen, quiet_ticks, cleanup_required = false, 0, false
  restored, unavailable, terminal_unavailable = 0, 0, {}
  local pc = q("GetFirstPC")
  if pc then q("SetLocalNumber", pc, COUNTER_SLOT, 0) end
end
local function pending_any() return next(pending) ~= nil end
local function pending_failure()
  for _, state in pairs(pending) do if state.cleanup_required then return true end end
  return false
end

local cleanup_all

local function remove_owned(actor, state)
  -- A same-row disguise can leave the visible row unchanged after an owned
  -- apply. Do not release the exact token unless the protected remove itself
  -- succeeded as well as the independent original-row readback.
  local removed = call("RemoveEffect", actor, state.token)
  return removed and q("GetAppearanceType", actor) == state.original
end
local function forget_state(actor, state)
  pending[actor] = nil
  copies[actor] = nil
  if state == pc_state then pc_state = nil end
end
local function resolve_state(actor, state, terminal)
  if not valid_living(actor) then
    if not state.unavailable then
      state.unavailable = true
      kp.print("[cursed:mirror] actor unavailable; exact cleanup unresolved")
    end
    if terminal then
      forget_state(actor, state)
      terminal_unavailable[actor] = state
      unavailable = unavailable + 1
      kp.print("[cursed:mirror] transition terminal: unavailable actor was not restored")
    end
    return false
  end
  if remove_owned(actor, state) then
    forget_state(actor, state)
    restored = restored + 1
    return true
  end
  state.cleanup_required = true
  return false
end

-- Store a strong reference to one newly constructed token before the void
-- apply. The same token is the only value ever passed to RemoveEffect.
local function apply_disguise(actor, target)
  local original = row(q("GetAppearanceType", actor))
  if not original then return false end
  local token = q("EffectDisguise", target)
  if not token then return false end
  local state = { original = original, target = target, token = token, cleanup_required = false }
  pending[actor] = state
  local request_ok = call("ApplyEffectToObject", DURATION_PERMANENT, token, actor, 0.0)
  if request_ok and q("GetAppearanceType", actor) == target then
    state.active = true
    return true, state
  end
  state.cleanup_required = true
  resolve_state(actor, state)
  return false
end

local function finish_if_resolved()
  if pending_any() then return end
  if unavailable == 0 then
    kp.print(("[cursed:mirror] restored %d owned disguises"):format(restored))
  else
    kp.print(("[cursed:mirror] cleanup ended with %d restored, %d unavailable"):format(restored, unavailable))
  end
  clear_run()
  set_armed(false)
end
cleanup_all = function(terminal)
  for actor, state in pairs(pending) do resolve_state(actor, state, terminal) end
  finish_if_resolved()
end

local function terminal_transition(reason)
  if pending_any() then
    cleanup_required = true
    cleanup_all(true)
    if pending_any() then
      -- The PC can persist over an area transition. Keep its strong token
      -- reference and remain disarmed; a later tick can retry exact cleanup.
      kp.print("[cursed:mirror] transition " .. reason .. "; exact cleanup unresolved")
      set_armed(false)
      return
    end
  else
    clear_run()
    set_armed(false)
  end
end

local function speak(actor, text, channel)
  if nwscript and type(nwscript.with_caller) == "function" then
    pcall(nwscript.with_caller, actor, function() q("SpeakString", text, channel) end)
  end
end
local function show_malak(pc)
  local vfx = q("EffectVisualEffect", VFX_DARK_LIGHTNING)
  if vfx then call("ApplyEffectToObject", DURATION_TEMPORARY, vfx, pc, 6.0) end
  call("SetGlobalFadeOut", 0.0, 0.1, 0.4, 0.0, 0.0)
  call("SetGlobalFadeIn", 0.1, 0.5, 0.0, 0.0, 0.0)
  speak(pc, "I am the Dark Lord.", 1)
end
local function show_copy(actor)
  local vfx = q("EffectVisualEffect", VFX_WHIRLWIND)
  if vfx then call("ApplyEffectToObject", DURATION_TEMPORARY, vfx, actor, 0.0) end
  speak(actor, "I am you.", 0)
end
function OnModuleLoad(relevant) terminal_transition("module load") end
function OnAreaEnter(area, entering, relevant) terminal_transition("area enter") end

function OnTick(tick, relevant)
  if pending_any() then
    for actor, state in pairs(pending) do
      if not valid_living(actor) then
        resolve_state(actor, state)
        cleanup_required = true
      end
    end
    if pending_failure() or cleanup_required then
      cleanup_all()
      return
    end
    local pc = q("GetFirstPC")
    if valid_living(pc) and yes(q("GetIsInCombat", pc)) then
      combat_seen, quiet_ticks = true, 0
    elseif combat_seen then
      quiet_ticks = quiet_ticks + 1
      if quiet_ticks >= SETTLE_TICKS then
        cleanup_required = true
        cleanup_all()
      end
    end
    return
  end
  if armed_flag then return end
  tick_count = tick_count + 1
  if tick_count >= ARM_TICKS then
    set_armed(true)
    kp.print("[cursed] armed")
  end
end

local function eligible_hostile(who, pc)
  return who ~= pc and valid_living(who) and not yes(q("IsObjectPartyMember", who))
end
function OnCreatureAttacked(creature, attacker, relevant)
  if not armed_flag or pending_failure() or cleanup_required then return end
  local pc = q("GetFirstPC")
  if not valid_living(pc) or yes(q("GetIsInConversation", pc)) then return end
  local hostile = creature == pc and attacker or (attacker == pc and creature or nil)
  if not hostile or not eligible_hostile(hostile, pc) or copies[hostile] then return end
  if not pc_state then
    original_pc_appearance = original_pc_appearance or row(q("GetAppearanceType", pc))
    if not original_pc_appearance then return end
    local active, state = apply_disguise(pc, MALAK)
    if not active then return end
    pc_state = state
    show_malak(pc)
  end
  if apply_disguise(hostile, original_pc_appearance) then
    copies[hostile] = true
    count = count + 1
    q("SetLocalNumber", pc, COUNTER_SLOT, count)
    show_copy(hostile)
    kp.print(("[cursed:mirror] hostile copy (#%d)"):format(count))
  end
end
