-- Object blaster (interim): the player's blaster bolts load a local placeable
-- model, and each creature the player damages gets one engine force-push.
--
-- Knockback label: "engine force-push, interim". It is the stock
-- EffectForcePushed applied with the player as caller, so the engine pushes the
-- target away from the player (projectile-impact-contract.md, native force-push
-- contract). It is not tumbling or ragdoll, and it is not timed to projectile
-- arrival: it runs from a confirmed player hit.
--
-- Trigger (Round 2 fix). `kp.events.OnCreatureDamaged` is a dead name in this
-- runtime: it hooks `vm.run_script` with `outer_event_id -1`
-- (src/generated/events.inc, docs/user/api-status.md "Dead names"), so
-- registration returns true but C++ never dispatches it
-- (src/runtime/hook_bodies.cpp:655,706 raise only OnRunScript/OnRunScriptDone).
-- `OnCreatureAttacked` is Live for NPC victims (docs/user/api-status.md), and
-- `20_fus_ro_dah.lua` already reads it from inside a hook. But it fires on
-- every attack, including a miss, so a push here also requires a confirmed
-- hit: the handler samples the target's own hit points and only proceeds if
-- they went down since the last time this script looked. The very first
-- attack this script ever sees against a given creature has no prior sample,
-- so it can only record a baseline and cannot be classified as a hit or a
-- miss; it never pushes. Every attack after that is classified correctly.
-- This is a documented, deliberate under-count on the first sighting of each
-- target, never an over-count: a miss can never look like a hit, because a
-- miss never lowers hit points.
--
-- Model selection uses the native kp.projectiles service. It needs a runtime
-- with that service (the frozen projectile build); otherwise start fails and
-- publishes state 9. Models stay local game assets and are never shipped.
--
-- Control is by PC local numbers, so a route or another script can drive it.
-- These are on the PC and persist into a save the same way any other local
-- number does; they are only meaningful while this script's phase is
-- 'running' (state 1 or 2) and are re-zeroed on every (re)arm, so a save/load
-- mid-run reads back the last-published values rather than resuming a push.
--   5  request, written by the driver: 1 start (first model), 2 switch to the
--      second model, 3 stop. The demo clears it to 0 once handled.
--   6  state, written by the demo: 4 ready, 1 running with the first model,
--      2 running with the second model, 3 stopped, 9 failed.
--   10 pushes applied since start.
--   11 confirmed player-damage events seen since start.
-- One push per confirmed damage event, so 10 == 11 while nothing failed.
-- Slots 10/11 are deliberately not 7/8: every script in scripts/examples/cursed
-- uses local number 7 as its own single-purpose counter (COUNTER_SLOT = 7,
-- e.g. 20_fus_ro_dah.lua), so 7 (and 8, the old slot this demo used before
-- Round 2) collide with that pack if it is ever deployed alongside this demo.
--
-- Oracle lines: "[object-blaster] push n=<pushes> event=<events> target=<id>",
-- "[object-blaster] ignored ...", "[object-blaster] selected model=<resref>",
-- "[object-blaster] stopped reason=<why> pushes=<n> events=<n>".

local blaster = {
  MODELS = { 'PLC_FootLker', 'PLC_Crate' },
  REQUEST = 5, STATE = 6, PUSHES = 10, EVENTS = 11,
  READY = 4, RUNNING_FIRST = 1, RUNNING_SECOND = 2, STOPPED = 3, FAILED = 9,
  ARM_TICKS = 200,
}
local DURATION_INSTANT = 0

local status = { phase = 'waiting', ticks = 0, pushes = 0, events = 0, ignored = 0, model = nil, bound = false, hp_seen = {} }
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

-- OnCreatureAttacked handler: `creature` is the one attacked, `attacker` the
-- one who swung (docs/user/api-status.md, data/events.toml:266-272). It
-- abstains (returns nothing) so the engine's own combat handling is
-- untouched. This fires on every attack, hit or miss, so the miss case is
-- excluded here by a confirmed hit-point drop rather than by trusting the
-- event alone.
function blaster.on_attacked(creature, attacker)
  if status.phase ~= 'running' then return end
  local ok, err = pcall(function()
    local pc = player()
    local why
    if not pc then why = 'no player'
    elseif attacker ~= pc then why = 'attacker is not the player'
    elseif creature == pc or yes(q('IsObjectPartyMember', creature)) then why = 'party member'
    elseif not yes(q('GetIsObjectValid', creature)) then why = 'invalid target'
    elseif yes(q('GetIsInConversation', pc)) then why = 'conversation'
    end
    if why then
      status.ignored = status.ignored + 1
      note(('ignored target=%s reason=%s'):format(tostring(creature), why))
      return
    end
    -- Confirmed-hit filter: compare this creature's current hit points to the
    -- last value this script sampled for it. A miss never lowers hit points,
    -- so it can never pass this check. A creature seen for the first time has
    -- no prior sample and only gets one recorded here, never a push.
    local hp_now = q('GetCurrentHitPoints', creature)
    local hp_before = status.hp_seen[creature]
    status.hp_seen[creature] = hp_now
    if hp_before == nil then
      note(('baseline target=%s hp=%s'):format(tostring(creature), tostring(hp_now)))
      return
    end
    if type(hp_now) ~= 'number' or type(hp_before) ~= 'number' or hp_now >= hp_before then
      status.ignored = status.ignored + 1
      note(('ignored target=%s reason=%s'):format(tostring(creature), 'no hit-point decrease (miss)'))
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
  status.hp_seen = {}
  publish(blaster.PUSHES, 0)
  publish(blaster.EVENTS, 0)
  local chosen, reason = choose_model(blaster.MODELS[1])
  if not chosen then fail(reason); return false end
  local bound = kp.events.register(kp.events.OnCreatureAttacked, blaster.on_attacked)
  if bound ~= true then fail('OnCreatureAttacked registration refused'); return false end
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

-- Teardown: unbind the attacked handler, return projectile loads to the stock
-- model, and restore the observation setting found at the first selection.
-- Safe to call more than once.
function blaster.stop(why)
  local problems = {}
  if status.bound then
    local ok, result = pcall(kp.events.unregister, kp.events.OnCreatureAttacked)
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
