-- HK-47 says something after every kill. Not always the same thing.
priority = 20

local lines = {
    "Statement: Another meatbag returned to the cosmic garbage disposal.",
    "Observation: That one screamed at a higher register than expected.",
    "Query: Should I remove the body, or would master prefer it left as a warning?",
    "Statement: Termination confirmed. Efficiency: acceptable.",
}

local rare = "Statement: I have several more efficient methods on file. Master has not yet asked."

-- The death event only names the corpse; GetLastKiller() is how you find who
-- actually did it.
function OnCreatureDeath(creature, relevant)
    if not kotor then return end
    local ok, killer = pcall(kotor.GetLastKiller)
    if not ok then return end
    local ok2, tag = pcall(kotor.GetTag, killer)
    if not ok2 or tag ~= "HK47" then return end

    local line = (math.random(20) == 1) and rare or lines[math.random(#lines)]
    pcall(kotor.SpeakString, line, 0)
end
