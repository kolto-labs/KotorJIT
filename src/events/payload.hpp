// Bounds-checked CScriptEvent reads and EventHandler argument shaping.
//
// The four parameter blocks are CExoArrayList, not fixed triples. Reading a
// slot as a raw offset treats the data pointer as a value. These helpers match
// the engine accessors: out of range is 0 / 0.0 / "" / OBJECT_INVALID.
#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <vector>

#include "events/contract.hpp"
#include "lua/value.hpp"

namespace kp::events {

struct ScriptEventView {
    void* data = nullptr;
};

std::uint16_t script_event_type(const ScriptEventView&);
int           script_event_int(const ScriptEventView&, int index);
float         script_event_float(const ScriptEventView&, int index);
std::uint32_t script_event_object(const ScriptEventView&, int index);
std::string   script_event_string(const ScriptEventView&, int index);

// True when layer-1 id is one of the three that DeleteEventData frees as
// CScriptEvent: SIGNAL_EVENT (10), SUMMON_CREATURE (0x18), AREA_TRANSITION (0x1A).
bool payload_is_script_event(int outer_event_id);

// OBJECT_SELF for an EventHandler `this`. Most types embed CGameObject at 0
// (id at +4). Areas embed it at +284. Modules do not start with CGameObject.
std::uint32_t object_id_from_handler(void* self, std::string_view hook_site);

struct HandlerFrame {
    void*         self = nullptr;
    std::uint32_t caller = kObjectInvalid;
    void*         payload = nullptr;
    std::uint32_t calendar_day = 0;
    std::uint32_t time_of_day = 0;
    std::string_view hook_site;
    int           outer_event_id = -1;
};

std::vector<lua::Value> shape_handler_args(const EventContract&,
                                           const HandlerFrame&);

}  // namespace kp::events
