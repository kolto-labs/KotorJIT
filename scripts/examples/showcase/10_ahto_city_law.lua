-- Manaan is neutral ground. The Selkath do not care who you are.
priority = 30

local strikes = 0

local function player()
    if not kotor then return nil end
    local ok, o = pcall(kotor.GetFirstPC)
    return ok and o or nil
end

local function on_manaan(pc)
    local ok, area = pcall(kotor.GetArea, pc)
    if not ok then return false end
    local ok2, tag = pcall(kotor.GetTag, area)
    return ok2 and tag and tag:sub(1, 3) == "man"
end

function OnCreatureAttacked(creature, attacker, relevant)
    local pc = player()
    if not pc then return end
    if attacker ~= pc and creature ~= pc then return end
    if not on_manaan(pc) then return end

    strikes = strikes + 1
    if strikes == 1 then
        pcall(kotor.SpeakString, "Selkath Security: violence is not tolerated in Ahto City.", 0)
    elseif strikes == 3 then
        pcall(kotor.SpeakString, "Selkath Security: this will be reported to the Bureau of Investigation.", 0)
    end
end

-- Manaan doesn't forget between visits.
function OnSave()
    return tostring(strikes)
end

function OnLoad(state)
    strikes = tonumber(state) or 0
end
