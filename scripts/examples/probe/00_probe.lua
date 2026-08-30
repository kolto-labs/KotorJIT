-- Says what the engine is doing, and decides none of it.
--
-- Two jobs. It is the harness's answer to "are we in gameplay yet" -- the stock
-- creature heartbeat cannot run before a module is up, so seeing it is proof
-- rather than a guess. And when an example does not appear to fire, this is what
-- says whether the event never arrived or the handler declined it.
--
-- Lowest priority and no return value anywhere: a probe that claimed an event
-- would change the thing it exists to observe.
priority = -1000

local seen = {}

local function note(what)
    seen[what] = (seen[what] or 0) + 1
    -- Once, then every hundredth. A heartbeat fires forever and an unthrottled
    -- line per event buries everything else in the log.
    local n = seen[what]
    if n == 1 or n % 100 == 0 then
        print(("[probe] %s x%d"):format(what, n))
    end
end

function OnRunScript(script_name, object_id, has_object, relevant)
    note("script:" .. tostring(script_name))
end

-- MainLoop cave: one log per 100 server frames so the file stays readable.
function OnTick(tick)
    note("OnTick")
end

-- Save/LoadScriptSituation caves. Returning a string from OnSave is what the
-- sidecar persists; OnLoad sees it on the next situation the VM restores.
function OnSave()
    note("OnSave")
    return "cave-witness"
end

function OnLoad(state)
    note("OnLoad")
end

function OnCreatureAttacked(creature, attacker, relevant)  note("OnCreatureAttacked") end
function OnCreatureDeath(creature, relevant)               note("OnCreatureDeath") end
function OnCreatureSpawn(creature, relevant)               note("OnCreatureSpawn") end
function OnCreatureEndCombatRound(creature, relevant)      note("OnCreatureEndCombatRound") end
function OnAreaEnter(area, entering, from_save)            note("OnAreaEnter") end
function OnModuleLoad()                                    note("OnModuleLoad") end
function OnModuleStart()                                   note("OnModuleStart") end
function OnModulePlayerEnter(player, relevant)             note("OnModulePlayerEnter") end
function OnModuleHeartbeat(day, time)                      note("OnModuleHeartbeat") end
function OnConsoleCommand(line, relevant)                  note("console:" .. tostring(line)) end

function OnScriptLoad(game, build)
    print(("[probe] watching %s (%s)"):format(tostring(game), tostring(build)))
end
