-- A line the first time you enter each world. Fires once per module prefix.
priority = 5

local seen = {}
local last_module = nil

local function q(name, ...)
    if not kotor then return nil end
    local fn = kotor[name]
    if not fn then return nil end
    local ok, v = pcall(fn, ...)
    return ok and v or nil
end

local lines = {
    dan = "The enclave courtyard is still. Too still.",
    man = "Salt air. Somewhere below, the kolto hisses.",
    tar = "Taris never sleeps. You hear it even from here.",
    kor = "The stone remembers every apprentice who walked it.",
    lev = "Metal corridors. No windows. The wrong kind of quiet.",
}

function OnTick(tick, relevant)
    if tick % 45 ~= 0 then return end
    local m = q("GetModuleName")
    if type(m) ~= "string" or m == last_module then return end
    last_module = m

    local key = m:lower():sub(1, 3)
    if seen[key] or not lines[key] then return end
    seen[key] = true
    print(("[arrival] %s"):format(key))
    q("SpeakString", lines[key], 0)
end

function OnSave()
    local keys = {}
    for k in pairs(seen) do keys[#keys + 1] = k end
    return table.concat(keys, ",")
end

function OnLoad(state)
    seen = {}
    last_module = nil
    if not state or state == "" then return end
    for part in state:gmatch("[^,]+") do seen[part] = true end
end
