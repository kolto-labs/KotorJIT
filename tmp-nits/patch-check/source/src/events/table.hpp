// The generated contract table and the two lookups the caves use.
//
// find() is by Lua callback name. find_by_site() is how an EventHandler cave
// picks a contract: hook site + layer-1 id, and for SIGNAL_EVENT the script
// event type as well. Names that only live on vm.run_script (heartbeat, death,
// spawn, ...) have outer_event_id == -1 and never come out of find_by_site.
#pragma once

#include <string_view>
#include <vector>

#include "events/contract.hpp"

namespace kp::events {

const std::vector<EventContract>& table();
const EventContract* find(std::string_view lua_name);
const EventContract* find_by_site(std::string_view hook_site,
                                  int outer_event_id,
                                  int script_event_type);

}  // namespace kp::events
