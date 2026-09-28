-- Drive the engine by routine, not by keystroke.
--
-- The cheat console still *delivers* these lines (DirectInput), but the
-- commands themselves call nwscript.call — warp, globals, conversation, fade.
-- Typing WASD or clicking LOAD GAME is what this exists to stop.
--
--   cover help
--   cover setb end_cut2_sith 1
--   cover getb end_cut2_sith
--   cover talk end_trask
--   cover jump end_trask
--   cover fade0
--   cover module end_m01aa
--   cover autosave
priority = 50

local function q(name, ...)
    if not nwscript or type(nwscript.call) ~= "function" then
        kp.print("[cover] nwscript.call is not available")
        return nil
    end
    local ok, a, b = pcall(nwscript.call, name, ...)
    if not ok then
        kp.print("[cover] " .. name .. " failed: " .. tostring(a))
        return nil
    end
    return a, b
end

local function valid(id)
    local v = id and q("GetIsObjectValid", id)
    return v == 1 or v == true
end

local function help()
    kp.print("[cover] setb <name> 0|1     SetGlobalBoolean")
    kp.print("[cover] setn <name> <int>   SetGlobalNumber")
    kp.print("[cover] getb <name>         GetGlobalBoolean")
    kp.print("[cover] getn <name>         GetGlobalNumber")
    kp.print("[cover] talk <tag> [dlg]    ActionStartConversation")
    kp.print("[cover] jump <tag>          JumpToObject")
    kp.print("[cover] fade0               SetGlobalFadeIn 0")
    kp.print("[cover] module <resref>     StartNewModule")
    kp.print("[cover] autosave            DoSinglePlayerAutoSave")
    kp.print("[cover] convo               GetIsConversationActive")
    kp.print("[cover] haste [n]           kp.speed — extra MainLoop ticks (1-16)")
    kp.print("[cover] pick <n>            prints the index only; no reply is chosen")
end

local function words(line)
    local t = {}
    for w in line:gmatch("%S+") do t[#t + 1] = w end
    return t
end

function OnConsoleCommand(line, relevant)
    if type(line) ~= "string" or line:sub(1, 5) ~= "cover" then return end
    if line ~= "cover" and line:sub(1, 6) ~= "cover " then return end
    local w = words(line)
    local cmd = w[2] or "help"
    if cmd == "help" then
        help()
    elseif cmd == "setb" and w[3] then
        q("SetGlobalBoolean", w[3], tonumber(w[4] or "1") ~= 0 and 1 or 0)
        kp.print("[cover] " .. w[3] .. "=" .. tostring(q("GetGlobalBoolean", w[3])))
    elseif cmd == "setn" and w[3] then
        q("SetGlobalNumber", w[3], tonumber(w[4] or "0") or 0)
        kp.print("[cover] " .. w[3] .. "=" .. tostring(q("GetGlobalNumber", w[3])))
    elseif cmd == "getb" and w[3] then
        kp.print("[cover] " .. w[3] .. "=" .. tostring(q("GetGlobalBoolean", w[3])))
    elseif cmd == "getn" and w[3] then
        kp.print("[cover] " .. w[3] .. "=" .. tostring(q("GetGlobalNumber", w[3])))
    elseif cmd == "talk" and w[3] then
        local npc = q("GetObjectByTag", w[3], 0)
        local pc = q("GetFirstPC")
        if not valid(npc) or not valid(pc) then
            kp.print("[cover] no object " .. w[3])
        elseif not nwscript or not nwscript.with_caller then
            kp.print("[cover] nwscript.with_caller missing — rebuild kphasor.dll")
        else
            local dlg = w[4] or ""
            nwscript.with_caller(pc, function()
                q("ActionStartConversation", npc, dlg)
            end)
            kp.print("[cover] talk " .. w[3] .. " dlg=" .. (dlg ~= "" and dlg or "(default)"))
        end
    elseif cmd == "jump" and w[3] then
        local dest = q("GetObjectByTag", w[3], 0)
        local pc = q("GetFirstPC")
        if not valid(dest) or not valid(pc) then
            kp.print("[cover] no object " .. w[3])
        elseif not nwscript or not nwscript.with_caller then
            kp.print("[cover] nwscript.with_caller missing — rebuild kphasor.dll")
        else
            nwscript.with_caller(pc, function()
                q("JumpToObject", dest, 1)
            end)
            kp.print("[cover] jump " .. w[3])
        end
    elseif cmd == "fade0" then
        q("SetGlobalFadeIn", 0.0, 0.0, 0.0, 0.0, 0.0)
        kp.print("[cover] fade in 0")
    elseif cmd == "module" and w[3] then
        q("StartNewModule", w[3])
        kp.print("[cover] module " .. w[3])
    elseif cmd == "autosave" then
        q("DoSinglePlayerAutoSave")
        kp.print("[cover] autosave")
    elseif cmd == "convo" then
        kp.print("[cover] active=" .. tostring(q("GetIsConversationActive")))
    elseif cmd == "haste" then
        if not kp or not kp.speed then
            kp.print("[cover] kp.speed missing — rebuild kphasor.dll")
        else
            local n = tonumber(w[3] or "4") or 4
            kp.print("[cover] speed=" .. tostring(kp.speed(n)))
        end
    elseif cmd == "pick" and w[3] then
        -- Visible-option index. No ChooseReply routine exists, so this only
        -- prints the number for the walker's log. Nothing here selects a
        -- reply; any digit keystroke comes from the harness, not this script.
        local n = tonumber(w[3]) or 1
        kp.print("[cover] pick=" .. tostring(n))
    else
        help()
    end
    return false
end
