-- A Sith trooper who spots you tells the others. They did not, before.
priority = 25

-- k_def_percept01 is the stock perception script, and it runs on whoever did the
-- perceiving -- so object_id is the sentry, and GetLastPerceived is what it just
-- noticed.
local PERCEIVED = "k_def_percept01"

local function norm_script(name)
  if type(name) ~= "string" then return "" end
  return name:gsub("%z+$", "")
end

local alarms = 0
local raised = {}
local last_module = nil

-- Every engine call goes through here: the API is absent until the runtime binds
-- the VM, and a routine can be missing on a build this script was not written
-- for. Asking by name rather than taking kotor.Whatever as an argument matters --
-- the argument form indexes the table before the guard ever runs.
local function q(name, ...)
    if not kotor then return nil end
    local fn = kotor[name]
    if not fn then return nil end
    local ok, v = pcall(fn, ...)
    return ok and v or nil
end

-- NWScript's TRUE is the integer 1, but what arrives in Lua depends on how the
-- bridge marshals a routine's return. Accept either rather than betting on one.
local function yes(v) return v == 1 or v == true end

local shouts = {
    "Intruder alert! Deck four!",
    "Contact! Republic personnel, still armed.",
    "They're not on the manifest. Sound it.",
}

function OnRunScript(script_name, object_id, has_object, relevant)
    script_name = norm_script(script_name)
    local m = q("GetModuleName")
    if type(m) == "string" and m ~= last_module then
        last_module = m
        raised = {}
    end
    if script_name ~= PERCEIVED then return end
    if raised[object_id] then return end

    local pc = q("GetFirstPC")
    if q("GetLastPerceived") ~= pc then return end
    if not yes(q("GetIsEnemy", pc, object_id)) then return end

    raised[object_id] = true
    alarms = alarms + 1
    print(("[alarm] %s raised the alarm (%d so far)")
          :format(tostring(q("GetName", object_id)), alarms))
    q("SpeakString", shouts[(alarms - 1) % #shouts + 1], 0)
end
