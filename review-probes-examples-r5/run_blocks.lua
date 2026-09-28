-- Runs each top-level do...end block of a prior probe file in isolation
-- (header prepended), so one restore-only assert cannot hide later blocks.
-- Adds one independent check per block: no min-one-HP routine was called
-- and no effect landed on the current GetFirstPC or a current party member.
-- usage: luajit run_blocks.lua <probe.lua> <probe-arg>
local probe, parg = arg[1], arg[2]
local text = assert(io.open(probe)):read('*a')
local lines = {}
for l in (text..'\n'):gmatch('(.-)\n') do lines[#lines+1] = l end
local header, blocks, cur = {}, {}, nil
for _, l in ipairs(lines) do
  if cur == nil and l == 'do' then cur = {l}
  elseif cur ~= nil then cur[#cur+1] = l; if l == 'end' then blocks[#blocks+1] = table.concat(cur, '\n'); cur = nil end
  elseif #blocks == 0 then header[#header+1] = l end
end
if #blocks == 0 then blocks = {table.concat(header, '\n')}; header = {} end
local head = table.concat(header, '\n')
local Fixture = dofile('tools/tests/examples/fixture.lua')
for i, b in ipairs(blocks) do
  local label = b:match('\n%s*[%w_]*%(?[\'"]([^\'"]+)') or ('block '..i)
  local stats = {calls = 0, violations = {}}
  -- Hook every fixture instance the block creates.
  package.loaded['kp_probe_fixture'] = nil
  local env = setmetatable({arg = {[0] = probe, parg}}, {__index = _G})
  env.dofile = function(p)
    if p == 'tools/tests/examples/fixture.lua' then
      local F = dofile(p); local new = F.new
      F.new = function(...)
        local f = new(...); local call = f.env.nwscript.call
        f.env.nwscript.call = function(name, ...)
          local a = {...}
          if name == 'SetMinOneHP' or name == 'GetMinOneHP' then stats.calls = stats.calls + 1 end
          if name == 'ApplyEffectToObject' then
            local id = a[3]; local pc = (f.overrides.GetFirstPC or function() return 1 end)()
            if id == pc or (f.objects[id] and f.objects[id].party == 1) then stats.violations[#stats.violations+1] = id end
          end
          return call(name, ...)
        end
        if os.getenv('KP_TOLERANT') == '1' then
          -- No settle timer and no unload handler exist by design; let the
          -- scenario run to its end so the safety check covers all of it.
          local fire = f.fire
          f.fire = function(self, i) if self.timers[i] then return fire(self, i) end return false end
          local load = f.load
          f.load = function(self, ...) load(self, ...); if self.env.OnScriptUnload == nil then self.env.OnScriptUnload = function() end end return self end
        end
        return f
      end
      return F
    end
    return dofile(p)
  end
  if os.getenv('KP_TOLERANT') == '1' then
    -- The probe's own asserts log instead of throwing, so a restore-only
    -- precondition cannot end the scenario early. The fixture keeps the real
    -- assert: it is loaded through the real dofile.
    env.assert = function(v, msg, ...) if not v then print('PROBE-ASSERT-FAILED	'..tostring(msg)) end return v, msg, ... end
  end
  env.loadfile = function(p) if p == 'tools/tests/examples/fixture.lua' then return function() return env.dofile(p) end end return loadfile(p) end
  local chunk, err = loadstring(head..'\n'..b, probe..'#'..i)
  print(('--- block %d'):format(i))
  if not chunk then print('LOADERR\t'..err) else
    setfenv(chunk, env)
    local ok, e = pcall(chunk)
    print((ok and 'RAN' or 'ERROR')..(ok and '' or '\t'..tostring(e)))
  end
  print(('SAFETY\tminonehp_calls=%d party_or_pc_effects=%d'):format(stats.calls, #stats.violations))
end
