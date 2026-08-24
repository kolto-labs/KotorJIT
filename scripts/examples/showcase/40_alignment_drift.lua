-- The game shows you a face changing. It never tells you the number.
priority = 0

local light = { "That felt right.", "Something in you settles." }
local dark  = { "That felt easy.", "Something in you loosens." }
local last = nil

-- The tick starts before the game has a player, so every reading is a question
-- rather than an assumption.
local function alignment()
    if not kotor then return nil end
    local ok, v = pcall(function()
        return kotor.GetAlignmentGoodEvil(kotor.GetFirstPC())
    end)
    return (ok and type(v) == "number") and v or nil
end

function OnTick(tick, relevant)
    if tick % 180 ~= 0 then return end
    local value = alignment()
    if not value then return end
    if last == nil then last = value; return end

    if math.floor(value / 10) == math.floor(last / 10) then last = value; return end
    local pool = (value > last) and light or dark
    last = value
    pcall(kotor.SpeakString, pool[math.random(#pool)], 0)
end
