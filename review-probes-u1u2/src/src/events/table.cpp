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

}  // namespace kp::events
