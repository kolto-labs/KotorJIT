// Host-side checks for EventHandler identity, CScriptEvent payload reads,
// argument shaping, and the thiscall cleanup the caves must emit.
//
// Nothing here launches the game. Address tables are parsed as files; the
// thiscall probes are functions compiled into this binary.

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

#include "api/enginestruct.hpp"
#include "events/contract.hpp"
#include "events/payload.hpp"
#include "events/situation.hpp"
#include "events/table.hpp"
#include "hooks/registry.hpp"
#include "hooks/thiscall.hpp"
#include "lua/host.hpp"
#include "lua/value.hpp"

namespace fs = std::filesystem;
using namespace kp;

namespace {

int g_failures = 0;

void check(bool ok, const char* what) {
    std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what);
    if (!ok) ++g_failures;
}

void section(const char* title) {
    std::printf("\n== %s ==\n", title);
}

#ifndef KP_REPO
#define KP_REPO "."
#endif

// Five stack args after this: the EventHandler caves must pop 0x14.
void KP_THISCALL event_handler_probe(void*, unsigned long, unsigned long,
                                     void*, unsigned long, unsigned long) {}

// Save: one stack arg. Load: three — both K1 callers push three.
int KP_THISCALL save_situation_probe(void*, void*) { return 1; }
int KP_THISCALL load_situation_probe(void*, void*, void*, void*) { return 1; }

bool code_has_ret_imm(const void* fn, std::uint16_t imm) {
    const auto* p = static_cast<const std::uint8_t*>(fn);
    // A small leaf is a handful of bytes; search a conservative window.
    for (int i = 0; i < 64; ++i) {
        if (p[i] == 0xC2 && p[i + 1] == static_cast<std::uint8_t>(imm) &&
            p[i + 2] == static_cast<std::uint8_t>(imm >> 8))
            return true;
    }
    return false;
}

void thiscall_cases() {
    section("thiscall cleanup");
    check(code_has_ret_imm(reinterpret_cast<const void*>(&event_handler_probe), 0x14),
          "EventHandler probe emits ret $0x14");
    check(code_has_ret_imm(reinterpret_cast<const void*>(&save_situation_probe), 0x04),
          "Save probe emits ret $0x4");
    check(code_has_ret_imm(reinterpret_cast<const void*>(&load_situation_probe), 0x0C),
          "Load probe emits ret $0xC");
}

void lookup_cases() {
    section("contract lookup");

    const events::EventContract* perc =
        events::find_by_site("event.creature", events::kSignalEvent, 1);
    check(perc != nullptr && perc->lua_name == "OnCreaturePerception",
          "event.creature + SIGNAL + type 1 -> OnCreaturePerception");

    const events::EventContract* spell =
        events::find_by_site("event.creature", events::kSignalEvent, 2);
    check(spell != nullptr && spell->lua_name == "OnCreatureSpellCastAt",
          "event.creature + SIGNAL + type 2 -> OnCreatureSpellCastAt");

    const events::EventContract* melee =
        events::find_by_site("event.creature", 0xF, -1);
    check(melee != nullptr && melee->lua_name == "OnCreatureAttacked",
          "event.creature + outer 0xF -> OnCreatureAttacked");

    check(events::find_by_site("event.creature", events::kSignalEvent, 0xA) == nullptr,
          "creature death (type 0xA) is not an EventHandler identity");
    check(events::find_by_site("vm.run_script", events::kSignalEvent, 1) == nullptr,
          "vm.run_script is never selected by EventHandler lookup");

    const events::EventContract* death = events::find("OnCreatureDeath");
    check(death != nullptr && death->hook_site == "vm.run_script" &&
              death->outer_event_id < 0,
          "OnCreatureDeath stays on vm.run_script with no outer id");

    const events::EventContract* load = events::find("OnModuleLoad");
    check(load != nullptr && load->hook_site == "event.module",
          "OnModuleLoad is keyed on event.module");

    // (site, outer[, type]) must be unique among EventHandler-keyed rows.
    bool unique = true;
    for (std::size_t i = 0; i < events::table().size(); ++i) {
        const auto& a = events::table()[i];
        if (a.outer_event_id < 0) continue;
        for (std::size_t j = i + 1; j < events::table().size(); ++j) {
            const auto& b = events::table()[j];
            if (b.outer_event_id < 0) continue;
            if (a.hook_site != b.hook_site) continue;
            if (a.outer_event_id != b.outer_event_id) continue;
            if (a.outer_event_id == events::kSignalEvent &&
                a.event_type != b.event_type)
                continue;
            unique = false;
            std::printf("  duplicate identity: %s / %s\n",
                        a.lua_name.c_str(), b.lua_name.c_str());
        }
    }
    check(unique, "EventHandler identities are unique");

    unsigned keyed = 0, run_script_named = 0;
    for (const auto& ev : events::table()) {
        if (ev.outer_event_id >= 0) ++keyed;
        if (ev.hook_site == "vm.run_script" && ev.lua_name != "OnRunScript" &&
            ev.lua_name != "OnRunScriptDone" && ev.lua_name != "OnDialogConditional")
            ++run_script_named;
    }
    check(keyed > 50, "most catalog rows are EventHandler-keyed");
    check(run_script_named >= 6, "named RunScript-only slots remain in the catalog");
}

void payload_cases() {
    section("CScriptEvent payload");

    int ints[2] = {7, 9};
    float floats[1] = {1.5f};
    std::uint32_t objs[1] = {0x2002u};
    struct {
        char* c_string;
        std::uint32_t length;
    } strings[1];
    char text[] = "hello";
    strings[0].c_string = text;
    strings[0].length = 5;

    alignas(4) unsigned char raw[0x34] = {};
    std::uint16_t type = 1;
    std::memcpy(raw + 0x00, &type, 2);

    struct List { void* data; std::int32_t size; std::int32_t cap; };
    List il{ints, 2, 2};
    List fl{floats, 1, 1};
    List sl{strings, 1, 1};
    List ol{objs, 1, 1};
    std::memcpy(raw + 0x04, &il, sizeof il);
    std::memcpy(raw + 0x10, &fl, sizeof fl);
    std::memcpy(raw + 0x1C, &sl, sizeof sl);
    std::memcpy(raw + 0x28, &ol, sizeof ol);

    events::ScriptEventView view{raw};
    check(events::script_event_type(view) == 1, "event_type word at +0");
    check(events::script_event_int(view, 0) == 7, "int_params[0]");
    check(events::script_event_int(view, 1) == 9, "int_params[1]");
    check(events::script_event_int(view, 2) == 0, "int_params[2] OOR -> 0");
    check(events::script_event_float(view, 0) == 1.5f, "float_params[0]");
    check(events::script_event_object(view, 0) == 0x2002u, "object_params[0]");
    check(events::script_event_object(view, 1) == events::kObjectInvalid,
          "object_params[1] OOR -> OBJECT_INVALID");
    check(events::script_event_string(view, 0) == "hello", "string_params[0]");
    check(events::script_event_string(view, 1).empty(), "string_params[1] OOR -> empty");

    check(events::payload_is_script_event(10), "SIGNAL_EVENT carries CScriptEvent");
    check(events::payload_is_script_event(0x18), "0x18 carries CScriptEvent");
    check(!events::payload_is_script_event(0xF), "melee-attacked payload is not CScriptEvent");

    alignas(4) unsigned char creature[16] = {};
    std::uint32_t cid = 0x1001u;
    std::memcpy(creature + 4, &cid, 4);
    check(events::object_id_from_handler(creature, "event.creature") == 0x1001u,
          "creature this -> id at +4");

    alignas(4) unsigned char area[300] = {};
    std::uint32_t aid = 0x3003u;
    std::memcpy(area + 288, &aid, 4);
    check(events::object_id_from_handler(area, "event.area") == 0x3003u,
          "area this -> id at +288");
}

void shape_and_host_cases() {
    section("arg shaping + Lua dispatch");

    const events::EventContract* ev = events::find("OnCreaturePerception");
    if (ev == nullptr) {
        check(false, "OnCreaturePerception is in the table");
        return;
    }
    check(ev->blocking && ev->args.size() == 3, "perception is blocking with 3 args");
    check(ev->args[0].source == "this" && ev->args[1].source == "object_params[0]" &&
              ev->args[2].source == "int_params[0]",
          "perception sources are this / object_params[0] / int_params[0]");

    int how = 1;
    std::uint32_t perceived = 0x2002u;
    struct List { void* data; std::int32_t size; std::int32_t cap; };
    List il{&how, 1, 1};
    List ol{&perceived, 1, 1};
    alignas(4) unsigned char raw[0x34] = {};
    std::uint16_t type = 1;
    std::memcpy(raw + 0x00, &type, 2);
    std::memcpy(raw + 0x04, &il, sizeof il);
    std::memcpy(raw + 0x28, &ol, sizeof ol);

    alignas(4) unsigned char creature[16] = {};
    std::uint32_t cid = 0x1001u;
    std::memcpy(creature + 4, &cid, 4);

    events::HandlerFrame frame;
    frame.self = creature;
    frame.caller = 0x9999u;
    frame.payload = raw;
    frame.hook_site = "event.creature";
    frame.outer_event_id = events::kSignalEvent;

    const std::vector<lua::Value> args = events::shape_handler_args(*ev, frame);
    check(args.size() == 3, "shaped arg count matches contract");

    const fs::path dir = fs::temp_directory_path() / "kp_eventtest_scripts";
    fs::create_directories(dir);
    {
        std::ofstream f(dir / "perc.lua");
        f << "function OnCreaturePerception(creature, perceived, how, relevant)\n"
             "  if creature == 4097 and perceived == 8194 and how == 1 then\n"
             "    return false\n"
             "  end\n"
             "  return true\n"
             "end\n";
    }

    lua::Host host({dir.string(), /*error_budget=*/3, /*hot_reload=*/false, {}});
    std::vector<std::string> errors;
    const unsigned loaded = host.load_all(errors);
    for (const auto& e : errors) std::printf("  load error: %s\n", e.c_str());
    check(loaded == 1, "test script loaded");

    const events::Outcome outcome = host.dispatch(*ev, args);
    check(outcome.claimed && !outcome.bool_result,
          "Lua claimed a block from the shaped perception args");

    events::Outcome nobody;
    nobody.claimed = false;
    check(!events::blocking_verdict(*ev, nobody).skip_original,
          "abstain does not skip the original");
    events::Outcome yes;
    yes.claimed = true;
    yes.bool_result = true;
    check(!events::blocking_verdict(*ev, yes).skip_original,
          "true does not skip the original");
    events::Outcome no;
    no.claimed = true;
    no.bool_result = false;
    check(events::blocking_verdict(*ev, no).skip_original,
          "false skips the original on a blocking contract");

    fs::remove_all(dir);
}

void command_bound_cases() {
    section("KPM command bound");
    const std::uint8_t stock[] = {
        0x8B, 0x54, 0x24, 0x04, 0x81, 0xFA, 0x04, 0x03, 0x00, 0x00,
    };
    const std::uint8_t kpm[] = {
        0x8B, 0x54, 0x24, 0x04, 0x81, 0xFA, 0xE8, 0x03, 0x00, 0x00,
    };
    std::uint32_t n = 0;
    check(api::decode_execute_command_bound(stock, sizeof stock, n) && n == 0x304,
          "stock ExecuteCommand bound is 772");
    check(api::decode_execute_command_bound(kpm, sizeof kpm, n) && n == 1000,
          "KPM-patched bound is 1000");
}

void situation_cases() {
    section("OnSave / OnLoad sidecar");
    const fs::path path = fs::temp_directory_path() / "kp_eventtest_situation.dat";
    check(events::write_situation_blob(path.string(), "party=wounded"),
          "write situation blob");
    check(events::read_situation_blob(path.string()) == "party=wounded",
          "read situation blob");
    fs::remove(path);
}

void address_table_cases() {
    section("address tables");

    const char* files[] = {
        "data/addresses/k1_gog_103.json",
        "data/addresses/k1_steam_103.json",
        "data/addresses/k1_steam_103_unpacked.json",
        "data/addresses/k2_gog_aspyr.json",
    };
    // The caves this work installs on the supported, target-verified tables.
    const char* caves[] = {
        "event.creature", "event.door", "event.placeable", "event.trigger",
        "event.module", "event.area", "event.encounter", "event.aoe",
        "event.store", "event.waypoint",
        "vm.save_script_situation", "vm.load_script_situation",
        "vm.run_script", "app.server_main_loop",
    };

    for (const char* rel : files) {
        const fs::path path = fs::path(KP_REPO) / rel;
        hooks::AddressTable table;
        std::string error;
        const bool loaded = hooks::AddressTable::load_file(path.string(), table, error);
        check(loaded, rel);
        if (!loaded) {
            std::printf("    %s\n", error.c_str());
            continue;
        }
        unsigned ok = 0;
        for (const char* name : caves) {
            const hooks::Site* s = table.find(name);
            if (s != nullptr && s->resolved && s->kind == hooks::SiteKind::Detour)
                ++ok;
            else
                std::printf("    unresolved: %s in %s\n", name, rel);
        }
        char buf[160];
        std::snprintf(buf, sizeof buf, "%s: %u/%zu EventHandler/save/load/core sites resolved",
                      rel, ok, sizeof caves / sizeof caves[0]);
        check(ok == sizeof caves / sizeof caves[0], buf);

        const hooks::Site* creature = table.find("event.creature");
        if (creature != nullptr && !creature->expected.empty())
            check(creature->expected.size() >= 5,
                  "event.creature expected_bytes wide enough to detour when present");
    }
}

}  // namespace

int main() {
    thiscall_cases();
    lookup_cases();
    payload_cases();
    shape_and_host_cases();
    command_bound_cases();
    situation_cases();
    address_table_cases();

    std::printf("\n%d failure(s)\n", g_failures);
    return g_failures == 0 ? 0 : 1;
}
