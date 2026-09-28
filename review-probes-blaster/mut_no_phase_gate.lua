-- Object blaster (interim): the player's blaster bolts load a local placeable
-- model, and each creature the player damages gets one engine force-push.
--
-- Knockback label: "engine force-push, interim". It is the stock
-- EffectForcePushed applied with the player as caller, so the engine pushes the
-- target away from the player (projectile-impact-contract.md, native force-push
-- contract). It is not tumbling or ragdoll, and it is not timed to projectile
-- arrival: it runs from the damaged creature's ScriptDamaged event.
--
-- Model selection uses the native kp.projectiles service. It needs a runtime
-- with that service (the frozen projectile build); otherwise start fails and
-- publishes state 9. Models stay local game assets and are never shipped.
--
-- Control is by PC local numbers, so a route or another script can drive it:
--   5  request, written by the driver: 1 start (first model), 2 switch to the
--      second model, 3 stop. The demo clears it to 0 once handled.
--   6  state, written by the demo: 4 ready, 1 running with the first model,
--      2 running with the second model, 3 stopped, 9 failed.
--   7  pushes applied since start.
--   8  damage events by the player seen since start.
-- One push per player damage event, so 7 == 8 while nothing failed.
--
-- Oracle lines: "[object-blaster] push n=<pushes> event=<events> target=<id>",
-- "[object-blaster] ignored ...", "[object-blaster] selected model=<resref>",
-- "[object-blaster] stopped reason=<why> pushes=<n> events=<n>".

local blaster = {
  MODELS = { 'PLC_FootLker', 'PLC_Crate' },
  REQUEST = 5, STATE = 6, PUSHES = 7, EVENTS = 8,
  READY = 4, RUNNING_FIRST = 1, RUNNING_SECOND = 2, STOPPED = 3, FAILED = 9,
  ARM_TICKS = 200,
}
local DURATION_INSTANT = 0

local status = { phase = 'waiting', ticks = 0, pushes = 0, events = 0, ignored = 0, model = nil, bound = false }
blaster.status = status

local function q(name, ...) return nwscript.call(name, ...) end
local function yes(v) return v == 1 or v == true end
local function note(text) kp.print('[object-blaster] ' .. text) end
local function player()
  local pc = q('GetFirstPC')
  if pc and yes(q('GetIsObjectValid', pc)) then return pc end
end
local function publish(slot, value)
  local pc = player()
  if pc then q('SetLocalNumber', pc, slot, value) end
end

-- One configured model or nil, reason. The service keeps its previous
-- configuration when it refuses a model.
local function choose_model(model)
  local service = kp.projectiles
  if type(service) ~= 'table' or type(service.configure) ~= 'function' then
    return nil, 'kp.projectiles is not in this runtime'
  end
  if status.prior_observing == nil and type(service.status) == 'function' then
    local ok, before = pcall(service.status)
    status.prior_observing = ok and type(before) == 'table' and before.observing == true
  end
  local ok, result, reason = pcall(service.configure, { model = model })
  if not ok then return nil, tostring(result) end
  if type(result) ~= 'table' then return nil, tostring(reason or 'configure refused') end
  if result.enabled ~= true or string.lower(tostring(result.model)) ~= string.lower(model) then
    return nil, 'configure did not publish ' .. model
  end
  status.model = model
  note('selected model=' .. model .. ' version=' .. tostring(result.version))
  return result
end

local function fail(why)
  blaster.stop('failed: ' .. tostring(why))
  status.phase = 'failed'
  publish(blaster.STATE, blaster.FAILED)
end

-- OnCreatureDamaged handler. It abstains (returns nothing), so the creature's
-- own damaged script still runs. The event only reaches living non-leader
-- creatures (data/events.toml OnCreatureDamaged).
function blaster.on_damaged(creature)
  local ok, err = pcall(function()
    local pc = player()
    local damager = nwscript.with_caller(creature, function() return q('GetLastDamager') end)
    local why
    if not pc then why = 'no player'
    elseif damager ~= pc then why = 'damager is not the player'
    elseif creature == pc or yes(q('IsObjectPartyMember', creature)) then why = 'party member'
    elseif not yes(q('GetIsObjectValid', creature)) then why = 'invalid target'
    elseif yes(q('GetIsInConversation', pc)) then why = 'conversation'
    end
    if why then
      status.ignored = status.ignored + 1
      note(('ignored target=%s reason=%s'):format(tostring(creature), why))
      return
    end
    status.events = status.events + 1
    publish(blaster.EVENTS, status.events)
    nwscript.with_caller(pc, function()
      q('ApplyEffectToObject', DURATION_INSTANT, q('EffectForcePushed'), creature, 0.0)
    end)
    status.pushes = status.pushes + 1
    publish(blaster.PUSHES, status.pushes)
    note(('push n=%d event=%d target=%s'):format(status.pushes, status.events, tostring(creature)))
  end)
  if not ok then fail(err) end
end

function blaster.start()
  if status.phase == 'running' then return true end
  status.pushes, status.events, status.ignored = 0, 0, 0
  publish(blaster.PUSHES, 0)
  publish(blaster.EVENTS, 0)
  local chosen, reason = choose_model(blaster.MODELS[1])
  if not chosen then fail(reason); return false end
  local bound = kp.events.register(kp.events.OnCreatureDamaged, blaster.on_damaged)
  if bound ~= true then fail('OnCreatureDamaged registration refused'); return false end
  status.bound = true
  status.phase = 'running'
  publish(blaster.STATE, blaster.RUNNING_FIRST)
  note('started model=' .. chosen.model)
  return true
end

function blaster.switch_model()
  if status.phase ~= 'running' then return false end
  local chosen, reason = choose_model(blaster.MODELS[2])
  if not chosen then fail(reason); return false end
  publish(blaster.STATE, blaster.RUNNING_SECOND)
  return true
end

-- Teardown: unbind the damaged handler, return projectile loads to the stock
-- model, and restore the observation setting found at the first selection.
-- Safe to call more than once.
function blaster.stop(why)
  local problems = {}
  if status.bound then
    local ok, result = pcall(kp.events.unregister, kp.events.OnCreatureDamaged)
    if not ok or result ~= true then problems[#problems + 1] = 'unregister: ' .. tostring(result) end
    status.bound = false
  end
  local service = kp.projectiles
  if status.model and type(service) == 'table' and type(service.disable) == 'function' then
    local ok, result = pcall(service.disable)
    if not ok or type(result) ~= 'table' or result.enabled ~= false then
      problems[#problems + 1] = 'disable: ' .. tostring(ok and 'still enabled' or result)
    end
    -- configure also turns observation on; put back what was there before.
    if status.prior_observing == false and type(service.observe) == 'function' then
      local seen, after, why = pcall(service.observe, false)
      if not seen or type(after) ~= 'table' or after.observing ~= false then
        problems[#problems + 1] = 'observe(false): ' .. tostring(seen and why or after)
      end
    end
    status.model = nil
  end
  status.prior_observing = nil
  local was = status.phase
  status.phase = 'stopped'
  if was ~= 'stopped' then
    note(('stopped reason=%s pushes=%d events=%d ignored=%d'):format(tostring(why or 'request'), status.pushes, status.events, status.ignored))
  end
  if #problems > 0 then
    status.phase = 'failed'
    note('teardown problems: ' .. table.concat(problems, '; '))
    return false
  end
  return true
end

local function handle(request)
  if request == 1 then return blaster.start() end
  if request == 2 then return blaster.switch_model() end
  if request == 3 then
    local ok = blaster.stop('request')
    publish(blaster.STATE, ok and blaster.STOPPED or blaster.FAILED)
    return ok
  end
  return false
end

-- Poll the request slot. Nothing runs until ARM_TICKS frames after a load;
-- effects applied during a load or cutscene hung the client in earlier demos
-- (scripts/examples/cursed/20_fus_ro_dah.lua).
function blaster.poll()
  if status.phase == 'waiting' then
    status.ticks = status.ticks + 1
    if status.ticks < blaster.ARM_TICKS then return end
    if not player() then return end
    publish(blaster.REQUEST, 0)
    publish(blaster.PUSHES, 0)
    publish(blaster.EVENTS, 0)
    publish(blaster.STATE, blaster.READY)
    status.phase = 'ready'
    note('ready')
    return
  end
  local pc = player()
  if not pc then return end
  local request = q('GetLocalNumber', pc, blaster.REQUEST)
  if request == 0 then return end
  publish(blaster.REQUEST, 0)
  if status.phase == 'failed' then return end
  handle(request)
end

local function rearm(why)
  if status.phase == 'running' then blaster.stop(why) end
  status.phase, status.ticks = 'waiting', 0
end

function OnTick(tick, relevant) blaster.poll() end
function OnModuleLoad(relevant) rearm('module load') end
function OnAreaEnter(area, entering, from_save_game, relevant) rearm('area enter') end
function OnScriptUnload(relevant) if status.phase == 'running' then blaster.stop('unload') end end

return blaster
