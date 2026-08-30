-- Bastila's battle meditation, always on, never asked for.
priority = 20

local ATTACKED = "k_def_attacked01"
local COMBAT_END = "k_def_combend01"

local function norm_script(name)
  if type(name) ~= "string" then return "" end
  return name:gsub("%z+$", "")
end

local active = false
local rounds = 0

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

local function party()
    local n = q("GetPartyMemberCount")
    if type(n) ~= "number" then return {} end
    local out = {}
    for i = 0, n - 1 do
        local m = q("GetPartyMemberByIndex", i)
        if m then out[#out + 1] = m end
    end
    return out
end

local function bastila_conscious()
    local by_tag = q("GetObjectByTag", "bastila", 0)
    if by_tag and not yes(q("GetIsDead", by_tag)) then return by_tag end
    for _, m in ipairs(party()) do
        -- The tag is stored lowercase on the party blueprint ("bastila"), and
        -- comparing against the spelling everyone writes never matches.
        local tag = q("GetTag", m)
        if type(tag) == "string" and tag:lower() == "bastila"
           and not yes(q("GetIsDead", m)) then
            return m
        end
    end
    return nil
end

function OnRunScript(script_name, object_id, has_object, relevant)
    script_name = norm_script(script_name)
    if script_name == COMBAT_END then active = false; return end
    if script_name ~= ATTACKED or active then return end

    -- The victim is object_id. Only our own side's trouble is her business.
    if not yes(q("IsObjectPartyMember", object_id)) then return end
    if not bastila_conscious() then return end

    active = true
    rounds = rounds + 1
    local n = 0
    for _, m in ipairs(party()) do
        local eff = q("EffectAttackIncrease", 1, 0)
        if eff and q("ApplyEffectToObject", 1, eff, m, 6.0) then n = n + 1 end
    end
    print(("[meditation] round %d: steadied %d of the party"):format(rounds, n))
end
