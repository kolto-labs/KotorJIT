-- The game shows you a face changing. It never tells you the number.
priority = 0

local light = { "That felt right.", "Something in you settles." }
local dark  = { "That felt easy.", "Something in you loosens." }
local last = nil

-- The tick starts before the game has a player, so every reading is a question
-- rather than an assumption.
local function alignment()
    if not nwscript or type(nwscript.call) ~= "function" then return nil end
    local ok, v = pcall(function()
        -- GetGoodEvilValue is the 0..100 number. GetAlignmentGoodEvil returns
        -- the LIGHT/DARK/NEUTRAL constant, which reads as a plausible small
        -- integer and silently never crosses a threshold.
        return nwscript.call('GetGoodEvilValue',nwscript.call('GetFirstPC'))
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
    kp.print(("[conscience] %+d, now %d"):format(value - last, value))
    last = value
    pcall(nwscript.call, "SpeakString", pool[math.random(#pool)], 0)
end
