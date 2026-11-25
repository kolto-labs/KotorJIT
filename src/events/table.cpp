#include "events/table.hpp"

namespace kp::events {

const std::vector<EventContract>& table() {
    using events::ValueType;
    using events::Fallback;
    using events::EngineReturn;
    static const std::vector<EventContract> kEvents = {
#include "generated/events.inc"
    };
    return kEvents;
}

const EventContract* find(std::string_view lua_name) {
    for (const auto& ev : table())
        if (ev.lua_name == lua_name) return &ev;
    return nullptr;
}

const EventContract* find_by_site(std::string_view hook_site,
                                  int outer_event_id,
                                  int script_event_type) {
    if (outer_event_id < 0) return nullptr;
    for (const auto& ev : table()) {
        if (ev.outer_event_id < 0) continue;
        if (ev.hook_site != hook_site) continue;
        if (ev.outer_event_id != outer_event_id) continue;
        if (outer_event_id == kSignalEvent && ev.event_type != script_event_type)
            continue;
        return &ev;
    }
    return nullptr;
}

namespace {

// Lua names a hook body looks up directly (find_contract / events::find /
// Host::set_lifecycle), rather than through find_by_site. Every one of these
// has outer_event_id == -1 in the generated table, and is the reason
// dispatchable() cannot answer that half of the table by itself.
//
// Source of truth: `grep -rn 'find_contract(\|events::find(\|set_lifecycle'
// src/` -- currently src/runtime/runtime.cpp and src/runtime/hook_bodies.cpp.
// Same list for K1 and K2: both run the same hook bodies.
constexpr const char* kDirectDispatchNames[] = {
    "OnScriptLoad", "OnScriptUnload", "OnConsoleCommand", "OnRunScriptDone",
    "OnSave", "OnLoad", "OnTick", "OnRunScript",
    "OnDialogConditional", "OnScriptSituation", "OnPlayerSpawn",
    "OnCreatureHeartbeat", "OnCreatureSpawn", "OnCreatureDamaged",
    "OnCreatureDeath", "OnCreatureEndCombatRound", "OnCreatureEndDialogue",
    "OnPlaceableEndDialogue", "OnTriggerTrapTriggered", "OnTriggerHeartbeat",
    "OnCreatureStateScript", "OnAreaTransitionFail", "OnItemUse",
    "OnClientRequestedScript",
};

}  // namespace

bool dispatchable(const EventContract& ev) {
    if (ev.outer_event_id >= 0)
        return find_by_site(ev.hook_site, ev.outer_event_id, ev.event_type) == &ev;
    for (const char* name : kDirectDispatchNames)
        if (ev.lua_name == name) return true;
    return false;
}

}  // namespace kp::events
