-- Bastila's battle meditation, always on, never asked for.
priority = 20

local active = false

local function player()
    if not kotor then return nil end
    local ok, o = pcall(kotor.GetFirstPC)
    return ok and o or nil
end

local function bastila_conscious()
    if not kotor then return nil end
    local ok, n = pcall(kotor.GetPartyMemberCount)
    if not ok then return nil end
    for i = 0, n - 1 do
        local ok2, m = pcall(kotor.GetPartyMemberByIndex, i)
        if ok2 then
            local _, tag = pcall(kotor.GetTag, m)
            local _, dead = pcall(kotor.GetIsDead, m)
            local alive = (dead == 0) or (dead == false)
            if tag == "Bastila" and alive then return m end
        end
    end
    return nil
end

function OnCreatureAttacked(creature, attacker, relevant)
    if active then return end
    local pc = player()
    if not pc then return end
    if attacker ~= pc and creature ~= pc then return end
    if not bastila_conscious() then return end

    active = true
    local ok, n = pcall(kotor.GetPartyMemberCount)
    for i = 0, (ok and n or 1) - 1 do
        local ok2, m = pcall(kotor.GetPartyMemberByIndex, i)
        if ok2 then
            local ok3, eff = pcall(kotor.EffectAttackIncrease, 1)
            if ok3 and eff then pcall(kotor.ApplyEffectToObject, 1, eff, m, 6.0) end
        end
    end
end

function OnCreatureEndCombatRound(creature, relevant)
    if creature == player() then active = false end
end
