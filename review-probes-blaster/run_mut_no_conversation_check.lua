-- Host mock test for scripts/demos/object-blaster/object_blaster.lua.
-- Run from the repository root: luajit tools/tests/examples/object_blaster.lua
-- Controlled Lua boundary only: it checks requests and decisions, never engine
-- effects. Live displacement, projectile models and event delivery need the
-- scenario routes under scripts/harness/scenarios/object-blaster/.
local DEMO = '/home/brunner56/kp-live-20260922/review-probes-blaster/mut_no_conversation_check.lua'
local CATALOG = 'src/generated/routines_k1.inc'
local INVALID = 2130706432
local PC, TROOPER, ALLY, STRANGER = 1, 20, 2, 30
local ON_DAMAGED, ON_TICK = 1042, 7

local function new(options)
  options = options or {}
  local w = { calls = {}, prints = {}, locals = {}, caller = nil, damager = {}, conversation = 0, observing = options.observing == true,
    configured = {}, disabled = 0, bound = {}, register_calls = 0, unregister_calls = 0 }
  local objects = { [PC] = true, [TROOPER] = true, [ALLY] = true, [STRANGER] = true }
  local party = { [PC] = 1, [ALLY] = 1 }
  local routines = {
    GetFirstPC = function() return PC end,
    GetIsObjectValid = function(id) return objects[id] and 1 or 0 end,
    IsObjectPartyMember = function(id) return party[id] or 0 end,
    GetIsInConversation = function() return w.conversation end,
    GetLocalNumber = function(id, slot) return w.locals[slot] or 0 end,
    SetLocalNumber = function(id, slot, value) assert(id == PC, 'locals only on the PC'); w.locals[slot] = value end,
    -- K1 GetLastDamager takes no argument: it answers for the caller.
    GetLastDamager = function() return w.damager[w.caller] or INVALID end,
    EffectForcePushed = function() return { effect = 'EffectForcePushed', creator = w.caller } end,
    ApplyEffectToObject = function() end,
  }
  local env = setmetatable({}, { __index = _G })
  local service = {
    configure = function(t)
      assert(type(t) == 'table' and type(t.model) == 'string', 'configure takes {model=...}')
      w.configured[#w.configured + 1] = t.model
      if options.refuse then return nil, 'model is not installed' end
      w.version = (w.version or 0) + 1
      w.enabled, w.model, w.observing = true, t.model, true
      return { supported = true, enabled = true, observing = true, model = t.model, version = w.version }
    end,
    disable = function()
      w.disabled = w.disabled + 1; w.enabled = false
      return { supported = true, enabled = false, observing = w.observing, model = w.model or '', version = (w.version or 0) + 1 }
    end,
    observe = function(on)
      assert(type(on) == 'boolean', 'observe takes a boolean')
      w.observe_calls = (w.observe_calls or 0) + 1; w.observing = on
      return { supported = true, enabled = w.enabled == true, observing = on }
    end,
    status = function() return { supported = true, enabled = w.enabled == true, observing = w.observing == true } end,
  }
  if options.projectiles == false then service = nil end
  env.kp = {
    print = function(s) w.prints[#w.prints + 1] = s end,
    projectiles = service,
    events = {
      OnCreatureDamaged = ON_DAMAGED, OnTick = ON_TICK,
      register = function(event, fn)
        w.register_calls = w.register_calls + 1
        assert(type(fn) == 'function', 'handler must be a function')
        if options.refuse_register then return false end
        w.bound[event] = fn; return true
      end,
      unregister = function(event)
        w.unregister_calls = w.unregister_calls + 1
        w.bound[event] = nil; return true
      end,
    },
  }
  env.nwscript = {
    call = function(name, ...)
      local fn = routines[name]
      if not fn then error('undeclared fixture routine: ' .. name) end
      w.calls[#w.calls + 1] = { name = name, args = { ... }, caller = w.caller }
      return fn(...)
    end,
    with_caller = function(id, fn, ...)
      local previous = w.caller; w.caller = id
      local results = { pcall(fn, ...) }
      w.caller = previous
      if not results[1] then error(results[2], 0) end
      return unpack(results, 2)
    end,
  }
  local chunk = assert(loadfile(DEMO))
  setfenv(chunk, env)
  w.demo, w.env = chunk(), env
  function w.count(name) local n = 0 for _, c in ipairs(w.calls) do if c.name == name then n = n + 1 end end return n end
  function w.pushes() return w.count('ApplyEffectToObject') end
  function w.has(text) for _, s in ipairs(w.prints) do if s:find(text, 1, true) then return true end end return false end
  function w.tick(n) for _ = 1, n or 1 do env.OnTick(0, true) end end
  function w.arm() w.locals[5] = 1; w.tick(199); assert(w.locals[6] == nil, 'armed early'); w.tick(1); assert(w.locals[6] == 4 and w.locals[5] == 0, 'not ready after arm ticks') end
  function w.request(n) w.locals[5] = n; w.tick(1); assert(w.locals[5] == 0, 'request not cleared') end
  -- Dispatch the event the way the host does: through the registered binding.
  function w.damage(creature, damager)
    w.damager[creature] = damager
    local handler = w.bound[ON_DAMAGED]
    if handler then return handler(creature, true) end
  end
  return w
end

local passed = 0
local function test(name, fn)
  local ok, err = pcall(fn)
  if not ok then error('object_blaster [' .. name .. ']: ' .. tostring(err), 0) end
  passed = passed + 1
  print('PASS\tdemos/object-blaster/object_blaster.lua\t' .. name)
end

test('arming ignores a stale request and publishes ready', function()
  local w = new()
  w.arm()
  assert(#w.configured == 0 and w.register_calls == 0, 'stale request acted on')
  assert(w.locals[7] == 0 and w.locals[8] == 0)
end)

test('start selects the first model and binds the damaged handler', function()
  local w = new(); w.arm(); w.request(1)
  assert(#w.configured == 1 and w.configured[1] == 'PLC_FootLker', 'first selection')
  assert(w.bound[ON_DAMAGED] == w.demo.on_damaged, 'handler bound to OnCreatureDamaged')
  assert(w.locals[6] == 1 and w.has('selected model=PLC_FootLker'))
end)

test('switch selects the second model', function()
  local w = new(); w.arm(); w.request(1); w.request(2)
  assert(#w.configured == 2 and w.configured[2] == 'PLC_Crate', 'second selection')
  assert(w.locals[6] == 2 and w.bound[ON_DAMAGED] ~= nil)
end)

test('one player damage event gives exactly one push from the player', function()
  local w = new(); w.arm(); w.request(1)
  local result = w.damage(TROOPER, PC)
  assert(result == nil, 'handler must abstain so the stock damaged script runs')
  assert(w.pushes() == 1 and w.count('EffectForcePushed') == 1, 'exactly one push')
  local build, apply
  for _, c in ipairs(w.calls) do
    if c.name == 'EffectForcePushed' then build = c elseif c.name == 'ApplyEffectToObject' then apply = c end
  end
  assert(build.caller == PC and apply.caller == PC, 'push is built and applied with the player as caller')
  assert(apply.args[1] == 0 and apply.args[2].effect == 'EffectForcePushed' and apply.args[2].creator == PC, 'instant force-push')
  assert(apply.args[3] == TROOPER, 'push lands on the damaged creature')
  local damager_call
  for _, c in ipairs(w.calls) do if c.name == 'GetLastDamager' then damager_call = c end end
  assert(damager_call.caller == TROOPER and #damager_call.args == 0, 'damager read as the damaged creature')
  assert(w.locals[7] == 1 and w.locals[8] == 1)
  w.damage(TROOPER, PC); w.damage(TROOPER, PC)
  assert(w.pushes() == 3 and w.locals[7] == 3 and w.locals[8] == 3, 'one push per event, no batching or drops')
  assert(w.has('push n=3 event=3 target=20'))
end)

test('non-player damager, party victim and conversation give no push', function()
  local w = new(); w.arm(); w.request(1)
  w.damage(TROOPER, STRANGER)
  w.damage(TROOPER, INVALID)
  w.damage(ALLY, PC)
  w.conversation = 1; w.damage(TROOPER, PC); w.conversation = 0
  assert(w.pushes() == 0 and w.count('EffectForcePushed') == 0, 'no push')
  assert(w.locals[7] == 0 and w.locals[8] == 0, 'no damage event counted')
  assert(w.demo.status.ignored == 4 and w.has('reason=damager is not the player') and w.has('reason=party member'))
end)

test('a miss raises no damaged event and so no push', function()
  local w = new(); w.arm(); w.request(1)
  -- A miss applies no damage, so the engine never runs ScriptDamaged. Ticks
  -- keep polling; nothing else may push.
  w.tick(300)
  assert(w.pushes() == 0 and w.locals[7] == 0 and w.locals[8] == 0)
  w.damage(TROOPER, PC)
  assert(w.pushes() == 1, 'next real hit still pushes once')
end)

test('damage before start gives no push', function()
  local w = new(); w.arm()
  w.demo.on_damaged(TROOPER)
  assert(w.pushes() == 0 and w.count('GetLastDamager') == 0)
end)

test('stop unbinds the handler and restores stock bolts', function()
  local w = new(); w.arm(); w.request(1); w.damage(TROOPER, PC)
  w.request(3)
  assert(w.unregister_calls == 1 and w.bound[ON_DAMAGED] == nil, 'handler unbound')
  assert(w.disabled == 1 and w.enabled == false, 'projectile selection disabled')
  assert(w.observing == false and w.observe_calls == 1, 'observation returned to off, as found')
  assert(w.locals[6] == 3 and w.has('stopped reason=request pushes=1 events=1'))
  local before = w.pushes()
  w.damage(TROOPER, PC)
  w.demo.on_damaged(TROOPER)
  assert(w.pushes() == before, 'no push after teardown')
  w.request(3)
  assert(w.unregister_calls == 1 and w.disabled == 1 and w.locals[6] == 3, 'second stop is a no-op')
end)

test('stop keeps observation on when it was on before start', function()
  local w = new({ observing = true }); w.arm(); w.request(1); w.request(2); w.request(3)
  assert(w.disabled == 1 and w.enabled == false and w.observing == true and (w.observe_calls or 0) == 0)
end)

test('stop and start again resets counters', function()
  local w = new(); w.arm(); w.request(1); w.damage(TROOPER, PC); w.request(3); w.request(1)
  assert(w.locals[6] == 1 and w.locals[7] == 0 and w.locals[8] == 0 and w.bound[ON_DAMAGED])
  w.damage(TROOPER, PC)
  assert(w.locals[7] == 1 and w.locals[8] == 1)
end)

test('module load while running tears down', function()
  local w = new(); w.arm(); w.request(1)
  w.env.OnModuleLoad(true)
  assert(w.bound[ON_DAMAGED] == nil and w.disabled == 1 and w.has('stopped reason=module load'))
  w.locals[5] = 1; w.tick(199)
  assert(#w.configured == 1, 'requests wait for the next arm')
end)

test('script unload while running tears down', function()
  local w = new(); w.arm(); w.request(1)
  w.env.OnScriptUnload(true)
  assert(w.bound[ON_DAMAGED] == nil and w.disabled == 1)
end)

test('refused model fails closed without binding', function()
  local w = new({ refuse = true }); w.arm(); w.request(1)
  assert(w.locals[6] == 9 and w.register_calls == 0 and w.bound[ON_DAMAGED] == nil)
  assert(w.has('model is not installed'))
  w.request(1)
  assert(#w.configured == 1, 'failed demo ignores further requests')
end)

test('runtime without kp.projectiles fails closed', function()
  local w = new({ projectiles = false }); w.arm(); w.request(1)
  assert(w.locals[6] == 9 and w.register_calls == 0 and w.has('kp.projectiles is not in this runtime'))
end)

test('refused registration disables the selection', function()
  local w = new({ refuse_register = true }); w.arm(); w.request(1)
  assert(w.locals[6] == 9 and w.disabled == 1 and w.enabled == false)
end)

test('Lua names do not reuse NWScript routine names', function()
  local catalog = assert(io.open(CATALOG)):read('*a')
  local routines = {}
  for name in catalog:gmatch('{%d+, "([%w_]+)"') do routines[name] = true end
  assert(routines.GetLastDamager and routines.EffectForcePushed, 'catalog parse')
  local source = assert(io.open(DEMO)):read('*a')
  local code = source:gsub('%-%-[^\n]*', ''):gsub("'[^'\n]*'", "''"):gsub('"[^"\n]*"', '""')
  for word in code:gmatch('[%a_][%w_]*') do
    assert(not routines[word], 'Lua name shadows NWScript routine: ' .. word)
  end
  for name in source:gmatch("q%('([%w_]+)'") do
    assert(routines[name], 'unknown K1 routine ' .. name)
  end
end)

print('CASES\t' .. passed)
print('all checks passed')
