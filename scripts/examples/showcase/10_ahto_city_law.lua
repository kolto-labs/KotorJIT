-- Manaan is neutral ground. The Selkath do not care who you are.
priority = 30

local strikes = 0

-- k_def_attacked01 is the stock "I was attacked" script, and the engine runs it
-- on the victim -- so object_id is who got hit, and the aggressor has to be
-- asked for separately.
local ATTACKED = "k_def_attacked01"

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

-- Ask the module, not the area. Area tags are not what you would hope: the one
-- the party is standing in reports "untitled".
local function on_manaan()
    local m = q("GetModuleName")
    return type(m) == "string" and m:lower():sub(1, 3) == "man"
end

function OnRunScript(script_name, object_id, has_object, relevant)
    if script_name ~= ATTACKED then return end
    if not on_manaan() then return end

    local pc = q("GetFirstPC")
    local attacker = q("GetLastAttacker", object_id)
    if attacker ~= pc then return end

    strikes = strikes + 1
    print(("[ahto] strike %d witnessed on Manaan"):format(strikes))
    if strikes == 1 then
        q("SpeakString", "Selkath Security: violence is not tolerated in Ahto City.", 0)
    elseif strikes == 3 then
        q("SpeakString", "Selkath Security: this will be reported to the Bureau of Investigation.", 0)
    end
end

-- Manaan does not forget between visits.
function OnSave()  return tostring(strikes) end
function OnLoad(state) strikes = tonumber(state) or 0 end
