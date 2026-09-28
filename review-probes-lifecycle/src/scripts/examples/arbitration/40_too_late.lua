-- Runs after someone has already claimed, so it sees relevant = false. Its
-- return value is discarded whether or not it checks.
priority = 10

function OnRunScript(script, object, has_object, relevant)
    if not relevant then
        print("[40_too_late]  relevant=false, my answer will be ignored")
    end
    return true   -- discarded
end
