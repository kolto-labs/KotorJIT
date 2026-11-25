-- Prints the player's position and facing whenever either changes noticeably.
--
-- Nothing else surfaces this, and there is no visual way to confirm movement
-- happened under headless llvmpipe -- see docs/knowledgebase (or ask why the
-- world renders black there). A test that drives #key presses and wants to
-- know whether they actually moved the character deploys this alongside
-- 00_probe.lua and greps kotorjit.log for [trace] lines.
priority = -1500

local lx, ly, lz, lf

local function q(name, ...)
    if not nwscript or type(nwscript.call) ~= "function" then return nil end
    local ok, v = pcall(nwscript.call, name, ...)
    return ok and v or nil
end

function OnTick(tick, relevant)
    if tick % 10 ~= 0 then return end
    local pc = q("GetFirstPC")
    if not pc or q("GetIsObjectValid", pc) ~= 1 then return end

    local p = q("GetPosition", pc)
    if type(p) ~= "table" or type(p.x) ~= "number" then return end
    local f = q("GetFacing", pc)
    if type(f) ~= "number" then f = -1 end

    if lx == nil or math.abs(p.x - lx) > 0.02 or math.abs(p.y - ly) > 0.02
       or math.abs(p.z - lz) > 0.02 or math.abs(f - lf) > 0.3 then
        kp.print(("[trace] t=%d pos %.3f %.3f %.3f face %.2f"):format(tick, p.x, p.y, p.z, f))
        lx, ly, lz, lf = p.x, p.y, p.z, f
    end
end
