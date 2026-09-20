-- When a companion is badly hurt, someone says so out loud.
priority = 15

local DAMAGED = "k_def_damage01"
local warned = {}

local function norm_script(name)
  if type(name) ~= "string" then return "" end
  return name:gsub("%z+$", "")
end

local function q(name, ...)
    if not nwscript or type(nwscript.call) ~= "function" then return nil end
    local ok, v = pcall(nwscript.call, name, ...)
    return ok and v or nil
end

local function yes(v) return v == 1 or v == true end

local function hurt_line(tag)
    tag = type(tag) == "string" and tag:lower() or "?"
    if tag:find("bastila", 1, true) then return "Bastila! Stay with us!" end
    if tag:find("carth", 1, true) then return "Carth is hit - cover him!" end
    if tag:find("mission", 1, true) then return "Mission! Get down!" end
    if tag:find("zaalbar", 1, true) then return "Zaalbar is bleeding!" end
    if tag:find("jolee", 1, true) then return "Jolee needs a medpac!" end
    if tag:find("juhani", 1, true) then return "Juhani - fall back!" end
    if tag:find("canderous", 1, true) then return "Canderous is taking fire!" end
    if tag:find("hk47", 1, true) then return "HK-47 has sustained damage." end
    return "One of ours is down!"
end

function OnRunScript(script_name, object_id, has_object, relevant)
    script_name = norm_script(script_name)
    if script_name ~= DAMAGED then return end
    if not yes(q("IsObjectPartyMember", object_id)) then return end
    if warned[object_id] then return end

    local hp = q("GetCurrentHitPoints", object_id)
    local max = q("GetMaxHitPoints", object_id)
    if type(hp) ~= "number" or type(max) ~= "number" or max <= 0 then return end
    if hp / max > 0.35 then return end

    warned[object_id] = true
    local tag = q("GetTag", object_id)
    local line = hurt_line(tag)
    kp.print(("[wounded] %s below 35%%"):format(tostring(tag)))
    q("SpeakString", line, 0)
end
