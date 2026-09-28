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

// Whether some hook body can ever actually raise this contract in the running
// game -- the single question kp.events.register needs answered before it
// promises a script's handler will be called.
//
// Two disjoint ways an event reaches Lua:
//   * outer_event_id >= 0: the EventHandler caves route it, keyed on
//     (hook_site, outer_event_id[, script_event_type]). find_by_site is that
//     routing table, so asking it whether this exact contract is the one it
//     would return is the literal single source of truth for that half.
//   * outer_event_id == -1: no EventHandler cave carries it. It only fires if
//     some hook body looks the contract up by lua_name directly (RunScript,
//     console, save/load, tick, script lifecycle). That is a fact about the
//     C++ call sites, not about this table, so it cannot be derived from the
//     table alone -- kDirectDispatchNames in table.cpp names exactly those
//     lookups (grep find_contract(/events::find(/set_lifecycle across src/ to
//     audit it) and is the same list for K1 and K2 since both run the same
//     hook bodies.
//
// Everything else with outer_event_id == -1 (OnCreatureDamaged and its
// vm.run_script siblings) is a real script slot in the game with no dispatch
// site wired to it yet -- see docs/user/api-status.md "Dead names".
bool dispatchable(const EventContract& ev);

}  // namespace kp::events
