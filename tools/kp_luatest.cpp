// Exercises the Lua host without the game: load a script directory, dispatch an
// event, and print who claimed the result and why.
//
// This exists because the arbitration rule is the part of the design most easily
// got subtly wrong, and the rule is only checkable by running several scripts
// that disagree. Wiring it to a real game event first would mean debugging the
// rule and the hook at the same time.
//
// Usage:
//   kp_luatest <script-dir> <EventName> [arg ...]
//   kp_luatest <script-dir> --list

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "events/contract.hpp"
#include "lua/host.hpp"
#include "lua/value.hpp"

using namespace kp;

namespace {

const std::vector<events::EventContract>& table() {
    using events::ValueType;
    using events::Fallback;
    using events::EngineReturn;
    static const std::vector<events::EventContract> kEvents = {
#include "generated/events.inc"
    };
    return kEvents;
}

const char* state_name(lua::ScriptState s) {
    switch (s) {
    case lua::ScriptState::Loaded:       return "loaded";
    case lua::ScriptState::FailedToLoad: return "failed";
    case lua::ScriptState::Quarantined:  return "quarantined";
    case lua::ScriptState::Unloaded:     return "unloaded";
    }
    return "?";
}

// Args are typed by the contract, so "1" becomes a number or a string depending
// on what the event declares. Guessing from the text would make the harness
// disagree with the runtime about what a script receives.
lua::Value coerce(const std::string& text, events::ValueType t) {
    switch (t) {
    case events::ValueType::Bool:   return lua::Value::boolean(text == "true" || text == "1");
    case events::ValueType::Int:    return lua::Value::integer(std::strtoll(text.c_str(), nullptr, 10));
    case events::ValueType::Float:  return lua::Value::number(std::strtod(text.c_str(), nullptr));
    case events::ValueType::Object: return lua::Value::object(std::strtoul(text.c_str(), nullptr, 0));
    case events::ValueType::String: return lua::Value::str(text);
    case events::ValueType::None:   return lua::Value::none();
    }
    return lua::Value::none();
}

}  // namespace

int main(int argc, char** argv) {
    if (argc < 3) {
        std::fprintf(stderr,
                     "usage: kp_luatest <script-dir> <EventName> [arg ...]\n"
                     "       kp_luatest <script-dir> --list\n");
        return 2;
    }
    const std::string dir = argv[1];
    const std::string what = argv[2];

    lua::Host host({dir, /*error_budget=*/3, /*hot_reload=*/false, {}, {}});
    std::vector<std::string> errors;
    const unsigned loaded = host.load_all(errors);

    std::printf("loaded %u script(s) from %s\n", loaded, dir.c_str());
    for (const auto& e : errors) std::printf("  load error: %s\n", e.c_str());

    std::printf("\ndispatch order (priority desc, then filename):\n");
    for (const auto& s : host.scripts())
        std::printf("  %-24s priority=%-4d %s\n",
                    s->name().c_str(), s->priority(), state_name(s->state()));

    if (what == "--list") {
        std::printf("\nevents:\n");
        for (const auto& ev : table()) {
            std::printf("  %-22s args=%zu returns=%zu%s\n",
                        ev.lua_name.c_str(), ev.args.size(), ev.results.size(),
                        ev.blocking ? " blocking" : "");
        }
        return 0;
    }

    const events::EventContract* ev = nullptr;
    for (const auto& c : table())
        if (c.lua_name == what) { ev = &c; break; }
    if (!ev) { std::fprintf(stderr, "unknown event: %s\n", what.c_str()); return 2; }

    std::vector<lua::Value> args;
    for (std::size_t i = 0; i < ev->args.size(); ++i) {
        const int argi = 3 + int(i);
        args.push_back(argi < argc ? coerce(argv[argi], ev->args[i].type)
                                   : lua::Value::none());
    }

    // Repeating matters for the error budget: quarantine only shows up once a
    // script has failed the same callback often enough, which a single dispatch
    // can never demonstrate.
    unsigned repeats = 1;
    for (int i = 3; i + 1 < argc; ++i)
        if (std::strcmp(argv[i], "--repeat") == 0)
            repeats = unsigned(std::strtoul(argv[i + 1], nullptr, 10));

    std::printf("\ndispatching %s to %zu script(s) that define it%s:\n",
                ev->lua_name.c_str(), [&] {
                    std::size_t n = 0;
                    for (const auto& s : host.scripts())
                        if (s->state() == lua::ScriptState::Loaded && s->defines(ev->lua_name)) ++n;
                    return n;
                }(),
                repeats > 1 ? (", x" + std::to_string(repeats)).c_str() : "");

    events::Outcome out{};
    for (unsigned i = 0; i < repeats; ++i) {
        out = host.dispatch(*ev, args);
        host.advance_tick();
    }

    std::printf("\nresult\n");
    std::printf("  called      : %u\n", out.called);
    std::printf("  abstained   : %u\n", out.abstained);
    std::printf("  errored     : %u\n", out.errored);
    std::printf("  ignored     : %u  (answered, but someone claimed first)\n", out.ignored);
    std::printf("  reconciles  : %s\n",
                out.called == out.abstained + out.errored + out.ignored +
                              (out.claimed ? 1u : 0u) ? "yes" : "NO");
    std::printf("  claimed     : %s\n", out.claimed ? "yes" : "no (fallback applied)");
    if (out.claimed) std::printf("  claimed by  : %s\n", out.claimed_by.c_str());
    if (!ev->results.empty()) {
        switch (ev->results.front()) {
        case events::ValueType::String:
            std::printf("  value       : \"%s\"\n", out.string_result.c_str()); break;
        case events::ValueType::Bool:
            std::printf("  value       : %s\n", out.bool_result ? "true" : "false"); break;
        default:
            std::printf("  value       : %lld\n", (long long)out.int_result); break;
        }
    }
    if (ev->blocking && !out.bool_result)
        std::printf("  effect      : the game's handler is SUPPRESSED\n");

    bool any_err = false;
    for (const auto& s : host.scripts()) {
        if (s->errors().empty()) continue;
        if (!any_err) { std::printf("\nscript errors\n"); any_err = true; }
        for (const auto& e : s->errors())
            std::printf("  [%s] %s: %s\n", s->name().c_str(), e.callback.c_str(),
                        e.message.c_str());
        if (s->state() == lua::ScriptState::Quarantined)
            std::printf("  [%s] quarantined after %u errors\n",
                        s->name().c_str(), s->error_count());
    }
    return 0;
}
