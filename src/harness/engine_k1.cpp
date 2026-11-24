// The i386 harness adapter: Windows PE (MSVC __thiscall) and native Linux
// ELF (stack-this cdecl) object layouts. Not compiled on x86_64, where
// engine_unsupported.cpp stands in -- see that file. hooks/runtime cmake
// lists exactly one.
#if defined(__i386__) || defined(_M_IX86)
// The engine adapter body, and the K1 (GOG 1.03 / Steam-unpacked, same .text)
// parameters.
//
// Every engine call here replays a path the corpus shows the GUI taking, in
// the same order, with the same arguments. Where the corpus was read for an
// argument type the file:line is in the comment at the call. Root of those
// paths: the kotor_readable tree for K1__k1_win_gog_swkotor.exe; Dev is
// src/AspyrBuild/depot/KOTOR/PC_Source/Dev, UN is src/_unattributed.
//
// Conventions are hardcoded per call (RE audit 6): every load-side, dialog and
// timer call below is __thiscall on Windows and stack-`this` cdecl on the
// native ELF; call_this() picks the shape from the table's platform.
//
// Site names are the rows in data/hooksites.toml. Field rows carry offset and
// size; `sizeof` rows carry a record stride in size; g.app_manager carries the
// global's VA in addr.
#include "harness/fields.hpp"
#include "platform/naming.hpp"
#include "harness/chargen.hpp"

#include <algorithm>
#include <atomic>
#include <cctype>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iterator>
#include <system_error>

#include "runtime/internal.hpp"

namespace kp::harness {

// ------------------------------------------------------------------ Result --

namespace {
std::string g_build_label = "unknown";
}

Result Result::success() { return Result{true, {}}; }
Result Result::fail(std::string e) { return Result{false, std::move(e)}; }
Result Result::unsupported(std::string site) {
    return Result{false, "unsupported on " + g_build_label + ": " + std::move(site) + " unresolved"};
}

// ------------------------------------------------------- detour bodies -----
//
// client.set_game_speed: CClientExoAppInternal::SetGameSpeed(this, float)
//   K1 Dev/game/clientcore/clientexoappinternal.cpp:2803 (thiscall, one float)
//   The client loop calls it every non-loading frame with 1.0 or 0.25 after its
//   own timer snapshots (:10499-10568, :10645), and it only writes
//   snapshot_scale on five timers. Applying the harness scale on top, inside
//   the same call, is the re-apply point the design names: the engine's value
//   is preserved as a factor so the death-sequence slow-mo still slows.
//
// client.play_movies: CClientExoAppInternal::PlayMoviesInExoArrayList
//   K1 UN/K1__k1_win_gog_swkotor.exe_0060.cpp:10 (thiscall, five stack args,
//   ret 0x14). Its own disable_movies path is `return 0` before any side
//   effect and leaves *outResult alone (:23-27); the callers pre-zero it, and
//   writing 0 there is belt and braces.

namespace {

using SetGameSpeedEcx   = void (KP_THISCALL*)(void*, float);
using SetGameSpeedStack = void (__attribute__((cdecl)) *)(void*, float);
using PlayMoviesEcx     = int (KP_THISCALL*)(void*, void*, int*, int, int, void*);
using PlayMoviesStack   = int (__attribute__((cdecl)) *)(void*, void*, int*, int, int, void*);

std::atomic<void*> g_orig_set_game_speed{nullptr};
std::atomic<void*> g_orig_play_movies{nullptr};
std::atomic<float> g_harness_scale{1.0f};
std::atomic<float> g_engine_scale{1.0f};
std::atomic<bool>  g_movies_enabled{false};   // headless default: no Bink window
std::atomic<void*> g_client_internal_seen{nullptr};

void KP_THISCALL set_game_speed_body_ecx(void* self, float scale) {
    auto orig = reinterpret_cast<SetGameSpeedEcx>(g_orig_set_game_speed.load(std::memory_order_acquire));
    g_client_internal_seen.store(self, std::memory_order_release);
    g_engine_scale.store(scale, std::memory_order_release);
    if (orig == nullptr) return;
    orig(self, scale);
    const float k = g_harness_scale.load(std::memory_order_acquire);
    if (k != 1.0f) orig(self, scale * k);
}

void __attribute__((cdecl)) set_game_speed_body_stack(void* self, float scale) {
    auto orig = reinterpret_cast<SetGameSpeedStack>(g_orig_set_game_speed.load(std::memory_order_acquire));
    g_client_internal_seen.store(self, std::memory_order_release);
    g_engine_scale.store(scale, std::memory_order_release);
    if (orig == nullptr) return;
    orig(self, scale);
    const float k = g_harness_scale.load(std::memory_order_acquire);
    if (k != 1.0f) orig(self, scale * k);
}

int KP_THISCALL play_movies_body_ecx(void* self, void* movies, int* out_result, int wait, int p4,
                                     void* skippable) {
    auto orig = reinterpret_cast<PlayMoviesEcx>(g_orig_play_movies.load(std::memory_order_acquire));
    if (!g_movies_enabled.load(std::memory_order_acquire)) {
        if (out_result != nullptr && platform::is_readable(out_result, sizeof *out_result)) *out_result = 0;
        return 0;
    }
    if (orig == nullptr) return 0;
    return orig(self, movies, out_result, wait, p4, skippable);
}

int __attribute__((cdecl)) play_movies_body_stack(void* self, void* movies, int* out_result, int wait,
                                                  int p4, void* skippable) {
    auto orig = reinterpret_cast<PlayMoviesStack>(g_orig_play_movies.load(std::memory_order_acquire));
    if (!g_movies_enabled.load(std::memory_order_acquire)) {
        if (out_result != nullptr && platform::is_readable(out_result, sizeof *out_result)) *out_result = 0;
        return 0;
    }
    if (orig == nullptr) return 0;
    return orig(self, movies, out_result, wait, p4, skippable);
}

// The body shape is decided from the runtime's loaded table, because the
// detour pointer is taken before any adapter exists.
CallShape runtime_shape() {
    const hooks::AddressTable* t = runtime::Runtime::instance().table();
    return t == nullptr ? CallShape::ThisInEcx : call_shape_for_platform(t->platform_name());
}

}  // namespace

void* client_set_game_speed_detour() {
    if (runtime_shape() == CallShape::ThisOnStack)
        return reinterpret_cast<void*>(&set_game_speed_body_stack);
    return reinterpret_cast<void*>(&set_game_speed_body_ecx);
}

void* client_play_movies_detour() {
    if (runtime_shape() == CallShape::ThisOnStack)
        return reinterpret_cast<void*>(&play_movies_body_stack);
    return reinterpret_cast<void*>(&play_movies_body_ecx);
}

void bind_adapter_originals(const hooks::HookSet& set) {
    g_orig_set_game_speed.store(set.original("client.set_game_speed"), std::memory_order_release);
    g_orig_play_movies.store(set.original("client.play_movies"), std::memory_order_release);
}

// ------------------------------------------------------------ site names ---

const std::vector<const char*>& adapter_site_names() {
    static const std::vector<const char*> names = {
        // roots of every pointer chain
        "g.app_manager", "appmgr.client", "appmgr.server", "appmgr.reentrant_server_stats",
        "client.internal", "server.internal",
        // detours (originals used by the adapter)
        "client.set_game_speed", "client.play_movies", "client.get_paused_by_combat",
        "client.set_paused_by_combat", "client.get_auto_paused", "client.set_auto_paused",
        // load / save
        "gui.unpack_game", "app.create_server", "net.start_connect_to_session",
        "msg.request_status", "client.get_client_name", "client.set_player_character_name",
        "client.set_input_class", "client.disable_input", "app.set_load_from_savegame",
        "client.set_loading_savegame", "client.send_load_game_request",
        "client.send_save_game_request", "client.net_layer", "client.message_handler",
        "msg.change_door_state", "msg.unlock_object",
        "msg.attack", "server.get_player_creature_id",
        "msg.area_loaded", "client.player_creature_id",
        "app.update_client_game_objects",
        // module
        "app.get_module", "module.name", "app.set_move_to_module_pending",
        "app.set_move_to_module_string", "app.set_move_to_module_start_waypoint",
        // phase
        "server.server_mode", "server.loading_module", "server.move_to_module_pending",
        "server.pause_state", "client.input_class", "client.main_menu",
        "client.area_not_ready_to_display", "client.game_over_state",
        "stats.continue_message_processing", "stats.load_game_error",
        "client.gui_manager", "gui.panel_exists", "gui.remove_panel", "client.is_movie_playing",
        "gui.tutorial_box", "gui.controller_pause", "gui.tutorial_handle_input",
        "gui.messagebox_callback", "gui.messagebox_callback_context", "gui.messagebox_callback_arg",
        "gui.tutorial_unpause", "gui.modal_data", "gui.modal_size",
        "gui.container_handle_input",
        "gui.party_selection_accept_party", "gui.party_selection_vtable", "gui.initialized",
        "gui.party_selection_selected_count", "gui.party_selection_mode",
        "gui.party_selection_entry0_flags",
        "gui.status_summary_handle_input",
        "gui.messagebox_handle_input",
        "gui.show_sw_in_game_gui", "gui.hide_sw_in_game_gui",
        "gui.main_menu_new_game", "menu.newgame_button", "menu.ready", "gui.panel_bit_flags",
        "gui.control_active", "gui.panels_data", "gui.panels_size", "gui.class_selection_select_button",
        "chargen.class_controls", "chargen.class_control", "chargen.main_route_panel",
        "chargen.main_quick_panel", "chargen.child_main_panel", "chargen.main_visible_panel",
        "gui.main_chargen_set_visible_panel", "gui.main_chargen_begin_play",
        "client.movie_player", "movie.internal", "movie.playing", "gui.sw_gui_status",
        // dialog
        "client.gui_in_game", "client.get_in_game_gui", "gui.dialog_panel", "gui.dialog_active",
        "gui.dialog_pending", "gui.reply_count", "gui.reply_texts", "gui.reply_links",
        "dialog.panel_current_entry", "dialog.panel_visible_count", "gui.dialog_owner",
        "server.client_to_server_object_id", "server.get_game_object", "object.dialog_ptr",
        "object.dialog_send_pending", "dialog.current_entry", "dialog.current_reply",
        "dialog.entries", "dialog.entry", "dialog.node_strref", "dialog.select_reply",
        "dialog.skip_past", "gui.handle_dialog_selection", "object.stop_dialog",
        // time
        "client.get_world_timer", "client.get_pause_timer", "client.get_animation_timer",
        "server.get_world_timer", "server.get_pause_timer", "timer.set_fixed_snapshot_rate",
        "timer.pause_world_timer", "timer.unpause_world_timer", "timer.paused",
        // globals and journal
        "app.get_global_variable_table", "gvt.table", "gvt.identifiers", "gvt.identifier",
        "gvt.identifier_type_index", "gvt.bools", "gvt.numbers", "gvt.strings",
        "gvt.boolean_count", "gvt.number_count", "gvt.string_count",
        "app.get_party_table", "party.table", "journal.entries", "journal.data", "journal.size",
        "journal.entry", "journal.entry_tag", "journal.entry_state",
        // GUI-independent PC auto-level transaction
        "client.get_sw_party", "client.get_creature_by_object_id",
        "party.get_player_character", "party.set_leader", "client_party.count",
        "client_creature.party_menu_use_item",
        "client_party.member", "client_party.member_id",
        "client_creature.get_server_creature",
        "server.get_item_by_object_id", "creature.run_equip",
        "creature.inventory", "inventory.get_item_in_slot", "item.id", "item.possessor",
        "stats.auto_levelup", "stats.get_level", "stats.can_level_up",
        "object.id", "object.type", "door.locked", "door.lockable", "door.open_state",
        "creature.stats", "stats.experience",
    };
    return names;
}

// ------------------------------------------------------- construction ------

GameAdapter::GameAdapter(const char* name, const Layout& layout, const hooks::AddressTable& table,
                         std::uintptr_t image_base)
    : name_(name), build_(table.build()), lay_(layout),
      shape_(call_shape_for_platform(table.platform_name())) {
    g_build_label = build_.empty() ? std::string(name) : build_;
    if (image_base != 0 && table.image_base() != 0) delta_ = image_base - table.image_base();

    for (const hooks::Site& s : table.sites()) {
        Bound b;
        b.is_field = site_is_field(s);
        b.addr = s.addr != 0 ? s.addr + delta_ : 0;
        if (b.is_field) {
            b.offset = site_offset(s);
            b.size   = site_size(s);
            b.ok     = b.size != 0;
        } else {
            b.ok = s.resolved && b.addr != 0;
        }
        bound_[s.name] = b;
    }

    for (const char* n : adapter_site_names())
        if (!have(n)) missing_.push_back(n);

    log("adapter %s for build %s: %zu site(s) missing of %zu, shape=%s", name_, build_.c_str(),
        missing_.size(), adapter_site_names().size(),
        shape_ == CallShape::ThisOnStack ? "stack-this" : "thiscall");
    if (!missing_.empty()) {
        std::string list;
        for (const std::string& m : missing_) { if (!list.empty()) list += ", "; list += m; }
        log("missing: %s", list.c_str());
    }
}

void GameAdapter::log(const char* fmt, ...) const {
    char buf[1024];
    va_list ap;
    va_start(ap, fmt);
    std::vsnprintf(buf, sizeof buf, fmt, ap);
    va_end(ap);
    platform::log(platform::LogLevel::Info, "harness[%s]: %s", name_, buf);
}

const Bound* GameAdapter::find(const char* site) const {
    auto it = bound_.find(site);
    if (it == bound_.end() || !it->second.ok) return nullptr;
    return &it->second;
}

bool GameAdapter::have(const char* site) const { return find(site) != nullptr; }

Result GameAdapter::require(std::initializer_list<const char*> sites) const {
    for (const char* s : sites)
        if (!have(s)) return Result::unsupported(s);
    return Result::success();
}

int GameAdapter::off(const char* site, int layout_default) const {
    if (const Bound* b = find(site); b != nullptr && b->is_field) return static_cast<int>(b->offset);
    return layout_default;
}

int GameAdapter::stride(const char* site, int layout_default) const {
    if (const Bound* b = find(site); b != nullptr && b->is_field) return static_cast<int>(b->size);
    return layout_default;
}

unsigned GameAdapter::width(const char* site) const {
    if (const Bound* b = find(site); b != nullptr && b->is_field && b->size != 0) return b->size;
    return 4;
}

std::optional<std::int32_t> GameAdapter::rd(std::uintptr_t base, const char* site) const {
    const Bound* b = find(site);
    if (base == 0 || b == nullptr || !b->is_field) return std::nullopt;
    const auto at = at_offset(base, b->offset);
    if (!at) return std::nullopt;
    return read_int(*at, b->size);
}

std::optional<std::uintptr_t> GameAdapter::rd_ptr(std::uintptr_t base, const char* site) const {
    const Bound* b = find(site);
    if (base == 0 || b == nullptr || !b->is_field) return std::nullopt;
    const auto at = at_offset(base, b->offset);
    if (!at) return std::nullopt;
    return read_ptr(*at);
}

// The adapter never passes a null pointer as a `this` argument. Every site it
// calls is a member function, so a null there is a pointer chain that did not
// resolve, and the engine would dereference it inside code the harness cannot
// unwind. Refusing at the call turns that into a readable failure instead.
template <typename Ret, typename... Args>
std::optional<Ret> GameAdapter::call(const char* site, void* self, Args... args) const {
    const Bound* b = find(site);
    if (b == nullptr || b->is_field) return std::nullopt;
    if (self == nullptr) { log("call %s refused: null this", site); return std::nullopt; }
    HookBodyScope scope;
    return call_this<Ret, Args...>(shape_, b->addr, self, args...);
}

template <typename... Args>
bool GameAdapter::callv(const char* site, void* self, Args... args) const {
    const Bound* b = find(site);
    if (b == nullptr || b->is_field) return false;
    if (self == nullptr) { log("call %s refused: null this", site); return false; }
    HookBodyScope scope;
    call_this<void, Args...>(shape_, b->addr, self, args...);
    return true;
}

std::uintptr_t GameAdapter::via_call_or_field(const char* call_site, std::uintptr_t call_self,
                                              const char* field_site, std::uintptr_t field_base,
                                              bool field_is_embedded) const {
    if (call_self != 0 && have(call_site))
        if (const auto p = call<std::uintptr_t>(call_site, reinterpret_cast<void*>(call_self)); p) return *p;
    const Bound* b = find(field_site);
    if (field_base == 0 || b == nullptr || !b->is_field) return 0;
    const auto at = at_offset(field_base, b->offset);
    if (!at) return 0;
    if (field_is_embedded) return *at;
    return read_ptr(*at).value_or(0);
}

// -------------------------------------------------- the g_pAppManager chain -
//
// g.app_manager is a field row anchored at the global (K1 0x007A39FC): addr
// is the global's VA, offset 0, size 4. The client side has a second route:
// the SetGameSpeed detour sees CClientExoAppInternal as `this` every frame, so
// client-only reads keep working on a build that resolved the detour but not
// the global.

std::uintptr_t GameAdapter::manager() const {
    const Bound* b = find("g.app_manager");
    if (b == nullptr || b->addr == 0) return 0;
    const auto at = at_offset(b->addr, b->is_field ? b->offset : 0);
    if (!at) return 0;
    return read_ptr(*at).value_or(0);
}

std::uintptr_t GameAdapter::client_app() const {
    const std::uintptr_t m = manager();
    const auto at = at_offset(m, off("appmgr.client", lay_.mgr_client));
    if (!at) return 0;
    return read_ptr(*at).value_or(0);
}

std::uintptr_t GameAdapter::client_internal() const {
    const std::uintptr_t app = client_app();
    if (const auto at = at_offset(app, off("client.internal", lay_.app_internal)); at) {
        const std::uintptr_t in = read_ptr(*at).value_or(0);
        if (in != 0) return in;
    }
    return reinterpret_cast<std::uintptr_t>(g_client_internal_seen.load(std::memory_order_acquire));
}

std::uintptr_t GameAdapter::server_app() const {
    const auto at = at_offset(manager(), off("appmgr.server", lay_.mgr_server));
    if (!at) return 0;
    return read_ptr(*at).value_or(0);
}

std::uintptr_t GameAdapter::server_internal() const {
    const auto at = at_offset(server_app(), off("server.internal", lay_.app_internal));
    if (!at) return 0;
    return read_ptr(*at).value_or(0);
}

std::uintptr_t GameAdapter::stats() const {
    const auto at = at_offset(manager(), off("appmgr.reentrant_server_stats", lay_.mgr_stats));
    if (!at) return 0;
    return read_ptr(*at).value_or(0);
}

std::uintptr_t GameAdapter::gui_in_game() const {
    if (const auto g = rd_ptr(client_internal(), "client.gui_in_game"); g && *g != 0) return *g;
    const std::uintptr_t app = client_app();
    if (app == 0) return 0;
    // CClientExoApp::GetInGameGui(this): K1 Dev/game/clientcore/clientexoapp.cpp:191
    return call<std::uintptr_t>("client.get_in_game_gui", reinterpret_cast<void*>(app)).value_or(0);
}

// ------------------------------------------------------------------ phase --

Phase GameAdapter::phase(PhaseDetail* out) {
    PhaseDetail d;
    const std::uintptr_t sapp = server_app();
    const std::uintptr_t sint = server_internal();
    const std::uintptr_t cint = client_internal();
    const std::uintptr_t st   = stats();
    const bool have_server = manager() != 0 && sapp != 0;

    auto take = [](int& dst, std::optional<std::int32_t> v) { if (v) dst = *v; };
    take(d.server_mode, rd(sint, "server.server_mode"));
    take(d.loading_module, rd(sint, "server.loading_module"));
    take(d.move_pending, rd(sint, "server.move_to_module_pending"));
    take(d.pause, rd(sint, "server.pause_state"));
    // Autopause pauses the world and animation timers as well as setting
    // pause_state; a cleared pause byte with stalled timers is a silent
    // freeze (no movement, no combat rounds, no door animation), so the
    // timers are reported alongside it.
    if (have("timer.paused")) {
        int mask = 0;
        bool any = false;
        auto flag = [&](const char* site, std::uintptr_t app, int bit) {
            if (app == 0 || !have(site)) return;
            const auto t = call<std::uintptr_t>(site, reinterpret_cast<void*>(app));
            if (!t || *t == 0) return;
            if (const auto p = rd(*t, "timer.paused"); p) {
                any = true;
                if (*p != 0) mask |= bit;
            }
        };
        flag("client.get_world_timer", client_app(), 1);
        flag("server.get_world_timer", sapp, 2);
        flag("client.get_animation_timer", client_app(), 4);
        if (any) d.timers_paused = mask;
    }
    take(d.area_not_ready, rd(cint, "client.area_not_ready_to_display"));
    take(d.input_class, rd(cint, "client.input_class"));
    take(d.game_over, rd(cint, "client.game_over_state"));
    take(d.load_error, rd(st, "stats.load_game_error"));
    int cmp = -1;
    take(cmp, rd(st, "stats.continue_message_processing"));

    // movie: the call first, the field chain second (RE audit 4).
    const std::uintptr_t capp = client_app();
    if (have("client.is_movie_playing") && capp != 0) {
        // CClientExoApp::IsMoviePlaying(this): K1 UN/_005e.cpp:9497
        if (const auto r = call<int>("client.is_movie_playing", reinterpret_cast<void*>(capp)); r)
            d.movie = *r != 0 ? 1 : 0;
    } else if (const auto mp = rd_ptr(cint, "client.movie_player"); mp && *mp != 0) {
        const int oi = off("movie.internal", lay_.movie_internal);
        const int op = off("movie.playing", lay_.movie_playing);
        const auto mi = at_offset(*mp, oi);
        if (mi) {
            const std::uintptr_t internal = read_ptr(*mi).value_or(0);
            if (const auto pl = at_offset(internal, op); pl)
                if (const auto v = read_int(*pl, 4); v)
                    d.movie = *v != 0 ? 1 : 0;
        }
    }

    // menu: PanelExists(gui_manager, &main_menu->panel), a pointer compare that
    // is safe on the stale main_menu pointer (RE audit 4). Panel is at +0 of
    // CSWGuiMainMenu (K1 types.h:7385).
    if (const auto mm = rd_ptr(cint, "client.main_menu"); mm) {
        if (*mm == 0) {
            d.main_menu = 0;
        } else if (const auto mgr = rd_ptr(cint, "client.gui_manager"); mgr && *mgr != 0) {
            // int CSWGuiManager::PanelExists(this, CSWGuiPanel*): K1 Dev/libsource/SWGui/swgui.cpp:1490
            if (const auto r = call<int>("gui.panel_exists", reinterpret_cast<void*>(*mgr),
                                         reinterpret_cast<void*>(*mm)); r)
                d.main_menu = *r != 0 ? 1 : 0;
        }
    }

    // These are the exact panels appended by the two engine callbacks, never
    // guessed from a type or a screen. A state report only claims the current
    // stage while its corresponding panel remains in the manager's own list.
    const auto chargen_mgr = rd_ptr(cint, "client.gui_manager");
    const std::uintptr_t stage_panel = chargen_stage_ == ChargenStage::Class ? new_game_panel_
                                      : chargen_stage_ == ChargenStage::Route ? main_char_gen_panel_ : 0;
    if (chargen_stage_ != ChargenStage::None && chargen_mgr && *chargen_mgr != 0 &&
        panel_is_listed(*chargen_mgr, stage_panel)) {
        d.chargen = 1;
    } else if (chargen_stage_ != ChargenStage::None) {
        new_game_panel_ = 0;
        main_char_gen_panel_ = 0;
        chargen_stage_ = ChargenStage::None;
    }

    const std::uintptr_t gui = gui_in_game();
    int gui_status = -1, dialog_active = -1;
    take(gui_status, rd(gui, "gui.sw_gui_status"));
    take(dialog_active, rd(gui, "gui.dialog_active"));
    take(d.controller_pause, rd(gui, "gui.controller_pause"));
    if (const auto panel = rd_ptr(gui, "gui.tutorial_box"); panel && *panel != 0) {
        const auto mgr = rd_ptr(cint, "client.gui_manager");
        if (mgr && *mgr != 0) {
            if (const auto listed = call<int>("gui.panel_exists", reinterpret_cast<void*>(*mgr),
                                              reinterpret_cast<void*>(*panel)); listed) {
                d.tutorial = *listed != 0 ? 1 : 0;
            }
        }
    }
    // CSWGuiStatusSummary is retained by CGuiInGame even while it is not
    // displayed.  Its presence in the manager's panel list, rather than the
    // current modal-stack top alone, is the engine-owned predicate for an XP
    // / journal notification which still has an OK button.
    if (const auto panel = rd_ptr(gui, "gui.status_summary_panel"); panel && *panel != 0) {
        const auto mgr = rd_ptr(cint, "client.gui_manager");
        if (mgr && *mgr != 0) {
            if (const auto listed = call<int>("gui.panel_exists", reinterpret_cast<void*>(*mgr),
                                              reinterpret_cast<void*>(*panel)); listed)
                d.status_summary = *listed != 0 ? 1 : 0;
        }
    }
    if (const auto mgr = rd_ptr(cint, "client.gui_manager"); mgr && *mgr != 0) {
        if (const auto count = rd(*mgr, "gui.modal_size"); count && *count >= 0) {
            d.modal_count = *count;
            if (*count > 0) {
                const auto data = rd_ptr(*mgr, "gui.modal_data");
                const auto top_at = data && *data != 0
                    ? at_offset(*data, static_cast<std::int64_t>(*count - 1) * sizeof(std::uintptr_t))
                    : std::nullopt;
                const std::uintptr_t top = top_at ? read_ptr(*top_at).value_or(0) : 0;
                const std::uintptr_t vt = top != 0 ? read_ptr(top).value_or(0) : 0;
                const auto slot = at_offset(vt, 0x3c);
                const std::uintptr_t handler = slot ? read_ptr(*slot).value_or(0) : 0;
                const Bound* expected = find("gui.status_summary_handle_input");
                if (d.status_summary < 0 && expected != nullptr)
                    d.status_summary = handler == expected->addr ? 1 : 0;
            }
        }
    }

    if (out != nullptr) *out = d;
    if (manager() == 0) return Phase::Unknown;
    return classify_phase(d, have_server, cmp, gui_status, dialog_active);
}

std::string GameAdapter::module_name() {
    const std::uintptr_t sapp = server_app();
    if (sapp == 0 || !have("app.get_module") || !have("module.name")) return {};
    // CSWSModule* CServerExoApp::GetModule(this): K1 UN/_004a.cpp:6788; null when no module.
    const auto mod = call<std::uintptr_t>("app.get_module", reinterpret_cast<void*>(sapp));
    if (!mod || *mod == 0) return {};
    // module name CExoString at CSWSModule+0x5c, read in place (RE audit sites list).
    const auto at = at_offset(*mod, off("module.name", -1));
    if (!at) return {};
    std::string name = read_exostring_at(*at).value_or(std::string());
    // A module loaded out of a save carries the alias it was resolved through:
    // the field reads "CURRENTGAME:end_m01aa" after a load and "end_m01aa" on
    // the module the engine started with. The alias is where the file came
    // from, not the module's file resref. NWScript GetModuleFileName reads this
    // same field and strips the alias; GetModuleName instead reads the IFO's
    // localized display name. Only a leading ALIAS: is taken: a colon anywhere
    // else is a name this does not understand and leaves alone.
    const std::size_t colon = name.find(':');
    if (colon != std::string::npos && colon + 1 < name.size()) {
        bool alias = colon > 0;
        for (std::size_t i = 0; i < colon; ++i)
            if (std::isalpha(static_cast<unsigned char>(name[i])) == 0) alias = false;
        if (alias) name.erase(0, colon + 1);
    }
    return name;
}

// ------------------------------------------------------------ load / save --

namespace {

// UnpackGame's whole effect, done in the harness with plain file I/O.
//
// CSWGuiSaveLoad::UnpackGame 0x6caaf0 copies the save into FUTUREGAME:, nukes
// GAMEINPROGRESS: and renames one onto the other (K1 UN/_006c.cpp:3208-3245).
// What it copies is the members of the save's SAVEGAME.sav ERF, one file per
// member -- the same export LoadPCAutoSave does in the open with
// CERFFile::ExportFilesFromERF into GAMEINPROGRESS: (UN/_006c.cpp:3019-3053).
// Doing it here keeps the load path off an engine `this` the harness does not
// own, and the intermediate FUTUREGAME: directory is not needed: the engine's
// rename only exists so a half-written copy never becomes the live game.
//
// A plain copy of SAVEGAME.sav would not do: the server resolves
// GAMEINPROGRESS:<module>.sav, which is a member of that archive.
bool export_savegame_to_gameinprogress(const std::string& save_dir, const std::string& dest,
                                       std::vector<SaveErfMember>* members, std::string* err) {
    namespace fs = std::filesystem;

    std::string erf_path;
    for (const char* leaf : {"SAVEGAME.sav", "savegame.sav", "SAVEGAME.SAV"}) {
        const std::string p = save_dir + "/" + leaf;
        if (std::ifstream probe(p, std::ios::binary); probe) { erf_path = p; break; }
    }
    if (erf_path.empty()) { *err = "no SAVEGAME.sav in " + save_dir; return false; }

    std::ifstream in(erf_path, std::ios::binary);
    const std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(in)),
                                          std::istreambuf_iterator<char>());
    if (!save_erf_members(bytes, members, err)) { *err = erf_path + ": " + *err; return false; }

    std::error_code ec;
    fs::create_directories(fs::path(dest), ec);
    if (ec) { *err = "cannot create " + dest + ": " + ec.message(); return false; }

    // CleanDirectory before the export: a module left by an earlier load would
    // otherwise shadow the one this save carries. The names are collected first
    // and removed after, because removing entries during a directory walk can
    // skip entries, and a skipped entry is the stale module this is here for.
    std::vector<fs::path> stale;
    for (fs::directory_iterator it(fs::path(dest), ec), end; !ec && it != end; it.increment(ec)) {
        std::error_code kind;
        if (it->is_regular_file(kind)) stale.push_back(it->path());
    }
    for (const fs::path& p : stale) {
        std::error_code rm;
        fs::remove(p, rm);
    }

    for (const SaveErfMember& m : *members) {
        // save_erf_members already refused a member that runs past the file;
        // checked again here because this is the copy that would read out of
        // the buffer, and the two are far enough apart to drift.
        if (!span_ok(m.offset, m.size, bytes.size())) {
            *err = erf_path + ": member '" + m.name + "' runs past the file";
            return false;
        }
        const std::string out_path = dest + "/" + m.name;
        std::ofstream out(out_path, std::ios::binary | std::ios::trunc);
        if (out) out.write(reinterpret_cast<const char*>(bytes.data() + m.offset),
                           static_cast<std::streamsize>(m.size));
        if (!out) { *err = "cannot write " + out_path; return false; }
    }
    return true;
}

}  // namespace

bool GameAdapter::read_last_module(const std::string& dir, std::string* module, std::string* where) const {
    std::vector<std::string> roots;
    if (const char* e = kp::naming::env("SAVES_DIR"); e != nullptr && *e != '\0') roots.emplace_back(e);
    const std::string game_dir = runtime::directory_of(runtime::self_module_path());
    if (!game_dir.empty()) {
        roots.push_back(game_dir + "/saves");
        roots.push_back(game_dir + "/Saves");
    }
    if (const char* x = std::getenv("XDG_DATA_HOME"); x != nullptr && *x != '\0')
        roots.push_back(std::string(x) + "/aspyr-media/KOTOR2/saves");
    if (const char* h = std::getenv("HOME"); h != nullptr && *h != '\0')
        roots.push_back(std::string(h) + "/.local/share/aspyr-media/KOTOR2/saves");

    where->clear();
    for (const std::string& root : roots) {
        for (const char* leaf : {"savenfo.res", "SAVENFO.res", "SAVENFO.RES"}) {
            const std::string path = root + "/" + dir + "/" + leaf;
            std::ifstream in(path, std::ios::binary);
            if (!in) continue;
            std::vector<std::uint8_t> bytes((std::istreambuf_iterator<char>(in)),
                                            std::istreambuf_iterator<char>());
            const std::string m = savenfo_last_module(bytes);
            if (m.empty()) { *where = path + ": no LASTMODULE"; return false; }
            *module = m;
            *where = path;
            return true;
        }
        if (!where->empty()) *where += ", ";
        *where += root;
    }
    *where = "no savenfo.res for '" + dir + "' under " + *where +
             " (set HYPERSTIM_SAVES_DIR to the saves directory)";
    return false;
}

Result GameAdapter::load_save(const std::string& dir) {
    if (dir.empty() || dir.find('/') != std::string::npos || dir.find('\\') != std::string::npos)
        return Result::fail("load_save: dir must be a save folder name, not a path");

    // The main-menu branch of CSWGuiSaveLoad::LoadGame replayed in one client
    // tick (Dev/game/clientcore/swguisaveload.cpp:920-955, RE audit 1).
    const Result req = require({"g.app_manager", "app.create_server",
                                "net.start_connect_to_session", "msg.request_status",
                                "app.set_load_from_savegame",
                                "client.set_loading_savegame", "client.send_load_game_request",
                                "client.net_layer", "client.message_handler"});
    if (!req.ok) return req;

    std::string last_module, where;
    if (!read_last_module(dir, &last_module, &where)) return Result::fail("load_save: " + where);
    log("load_save '%s': LASTMODULE=%s from %s", dir.c_str(), last_module.c_str(), where.c_str());

    const bool remote_client = runtime::active_multiplayer_transport() != nullptr &&
        runtime::Runtime::instance().role() == multiplayer::Role::Client;
    const bool dedicated_server = runtime::active_multiplayer_transport() != nullptr &&
        runtime::Runtime::instance().role() == multiplayer::Role::Server;
    const std::uintptr_t mgr = manager();
    std::uintptr_t capp = client_app();
    if (mgr == 0 || capp == 0) return Result::fail("load_save: app manager or client not readable");

    // slot 0xffffffff makes the server's LoadGame use the name verbatim as the
    // directory (serverexoappinternal.cpp:4625-4651), so a checkpoint can carry
    // any name.
    constexpr std::uint32_t kVerbatimSlot = 0xffffffffu;
    OwnedExoString sdir(dir);
    OwnedExoString smodule(last_module);

    // 1. UnpackGame's job, done here rather than by the engine: the save's
    //    SAVEGAME.sav members land in the GAMEINPROGRESS: directory, which is
    //    where LoadModule looks for <module>.sav. The alias is ".\gameinprogress"
    //    unless the ini overrides it (CExoBaseInternal::LoadAliases, K1
    //    UN/_005e.cpp:4228), and the game runs with the install as its working
    //    directory. Calling the engine's UnpackGame is not an option: it is a
    //    __thiscall on a CSWGuiSaveLoad panel the harness does not have, and
    //    passing a null `this` to an engine function is a rule this adapter
    //    keeps.
    const std::string save_dir = where.substr(0, where.find_last_of("/\\"));
    std::string dest = runtime::directory_of(runtime::self_module_path());
    if (const char* e = kp::naming::env("GAMEINPROGRESS_DIR"); e != nullptr && *e != '\0')
        dest = e;
    else
        dest += "/gameinprogress";
    std::vector<SaveErfMember> members;
    std::string unpack_error;
    log("load_save: 1 export '%s/SAVEGAME.sav' -> '%s'", save_dir.c_str(), dest.c_str());
    if (!export_savegame_to_gameinprogress(save_dir, dest, &members, &unpack_error))
        return Result::fail("load_save: " + unpack_error);
    log("load_save: 1 exported %u file(s), first '%s'", static_cast<unsigned>(members.size()),
        members.empty() ? "" : members.front().name.c_str());

    // 2. CreateServer(app_manager, 0) only when no server exists (:924 on the
    //    menu branch; the in-game branch skips straight to the request).
    //
    //    The zero is not decoration. The decompile at UN/_0040.cpp:154 shows
    //    CreateServer taking only `this`, but that read is advisory and the
    //    shipped code disagrees: 0x00401380 ends in `ret 4` and forwards the
    //    stack argument at [esp+0x18] to CServerExoApp::StartServices. Calling
    //    it with no argument hands StartServices whatever the caller's frame
    //    happened to hold, and the game then jumps through it. Every engine
    //    caller pushes something first, and the two calls in
    //    CSWGuiSaveLoad::LoadGame (0x006cb331 and 0x006cb54e, `push 0`) are the
    //    branch this replay follows, so the argument here is 0.
    const bool had_server = server_app() != 0;
    if (!had_server) {
        log("load_save: 2 CreateServer(mgr=%08x, 0)%s", static_cast<unsigned>(mgr),
            remote_client ? " for client-side engine dependencies" : "");
        callv("app.create_server", reinterpret_cast<void*>(mgr), 0);
        log("load_save: 2 CreateServer returned");
    } else {
        log("load_save: 2 server exists, in-game branch");
    }
    const std::uintptr_t sapp = server_app();
    log("load_save: 2 server=%08x", static_cast<unsigned>(sapp));
    if (sapp == 0)
        return Result::fail("load_save: no server after CreateServer");

    // 3. Pause both world timers (:926-928). Optional: a build without the
    //    timer sites loads anyway, it just starts the clocks a tick early.
    unsigned paused = 0;
    if (have("timer.pause_world_timer")) {
        if (!dedicated_server && have("client.get_world_timer")) {
            const auto ct = call<std::uintptr_t>("client.get_world_timer", reinterpret_cast<void*>(capp));
            if (ct && *ct != 0) {
                callv("timer.pause_world_timer", reinterpret_cast<void*>(*ct));
                ++paused;
            }
        }
        if (have("server.get_world_timer")) {
            const auto stt = call<std::uintptr_t>("server.get_world_timer", reinterpret_cast<void*>(sapp));
            if (stt && *stt != 0) {
                callv("timer.pause_world_timer", reinterpret_cast<void*>(*stt));
                ++paused;
            }
        }
    }
    log("load_save: 3 paused %u world timer(s)", paused);

    // A split server prepares the authoritative save but must not manufacture
    // the local client used by the retail single-player path. The remote
    // client below supplies BNCS/status/load requests over the transport.
    if (dedicated_server) {
        callv("app.set_load_from_savegame", reinterpret_cast<void*>(sapp), 1);
        log("load_save: server role prepared save; awaiting remote client request");
        return Result::success();
    }

    if (!had_server) {
        const std::uintptr_t cint = client_internal();
        const auto net = rd_ptr(cint, "client.net_layer");
        const auto handler = rd_ptr(cint, "client.message_handler");
        if (!net || *net == 0) return Result::fail("load_save: client.net_layer not readable");
        if (!handler || *handler == 0) return Result::fail("load_save: client.message_handler not readable");

        // 4. StartConnectToSession(net, 0, &clientName, &"", 10, 0x10):
        //    bool __thiscall (CNetLayer*, ulong, CExoString*, CExoString*, ulong, ulong)
        //    UN/_005d.cpp:1536. Flag 0x10 makes the loopback player sys-admin,
        //    which is what lets the client's "sModule.Run" reach RunModule.
        //    clientName comes from CClientExoApp::GetClientName(this, CExoString* out)
        //    (clientexoapp.cpp:85): the engine constructs into our slot, so the
        //    buffer it allocates is deliberately not freed here. When that site
        //    is unresolved the name "test" stands in; the server only labels
        //    the player with it.
        OwnedExoString client_name("test");
        CExoString engine_name{nullptr, 0};
        CExoString* name_arg = client_name.ptr();
        if (have("client.get_client_name")) {
            call<std::uintptr_t>("client.get_client_name", reinterpret_cast<void*>(capp),
                                 reinterpret_cast<void*>(&engine_name));
            if (engine_name.c_string != nullptr && engine_name.length != 0) name_arg = &engine_name;
        }
        OwnedExoString empty("");
        log("load_save: 4 StartConnectToSession(net, 0, name, '', 10, 0x10)");
        const auto connected = call<int>("net.start_connect_to_session", reinterpret_cast<void*>(*net), 0u,
                                         reinterpret_cast<void*>(name_arg),
                                         reinterpret_cast<void*>(empty.ptr()), 10u, 0x10u);
        if (!connected || (*connected & 0xff) == 0)
            return Result::fail("load_save: StartConnectToSession refused (connect already in flight?)");

        // 5. SendPlayerToServerStatus_RequestStatus(message_handler): UN/_0067.cpp:1758
        log("load_save: 5 RequestStatus");
        callv("msg.request_status", reinterpret_cast<void*>(*handler));
    }

    // 6. SetPlayerCharacterName(client, &"test"): UN/_005e.cpp:9416. Optional
    //    on a save load, and a build without the site loads anyway: the PC
    //    comes from the save's Module.ifo through RunModule ->
    //    LoadPrimaryPlayer -> LoadCharacterFromIFO, and the only thing this
    //    call adds is a BIC open that fails silently
    //    (docs/harness-research/critic-re.md, CORRECTION section). Kept for
    //    fidelity with the GUI path where the site resolved.
    if (have("client.set_player_character_name")) {
        OwnedExoString test_name("test");
        log("load_save: 6 SetPlayerCharacterName('test')");
        callv("client.set_player_character_name", reinterpret_cast<void*>(capp),
              reinterpret_cast<void*>(test_name.ptr()));
    } else {
        log("load_save: 6 SetPlayerCharacterName skipped: site unresolved, the PC comes from the module");
    }

    // 7. SetInputClass(client, 0, 1) and DisableInput(client): :950-951,
    //    UN/_005e.cpp:9370 and :9662. Optional for a save load.
    if (have("client.set_input_class")) callv("client.set_input_class", reinterpret_cast<void*>(capp), 0, 1);
    if (have("client.disable_input")) callv("client.disable_input", reinterpret_cast<void*>(capp));
    log("load_save: 7 SetInputClass(0,1)=%s DisableInput=%s",
        have("client.set_input_class") ? "yes" : "skipped", have("client.disable_input") ? "yes" : "skipped");

    // 8. SetLoadFromSaveGame(server, 1) UN/_004a.cpp:8129; SetLoadingSaveGame(client, 1) UN/_005e.cpp:11281.
    log("load_save: 8 SetLoadFromSaveGame(1), SetLoadingSaveGame(1)");
    // The split client's in-process server is a paused compatibility shell,
    // not an authority, but it must load the same module because retail K1 UI
    // code directly reads CServerExoApp::GetModule().  Its network replies are
    // suppressed by the transport detour.
    load_step_ = LoadStep::Idle;
    load_from_save_observed_ = false;
    load_server_internal_ = 0;
    callv("app.set_load_from_savegame", reinterpret_cast<void*>(sapp), 1);
    callv("client.set_loading_savegame", reinterpret_cast<void*>(capp), 1);
    load_server_internal_ = server_internal();
    load_from_save_observed_ = load_server_internal_ != 0 &&
        rd(load_server_internal_, "server.load_from_savegame").value_or(-1) == 1;

    // 9. SendLoadGameRequest(client, slot, &dir, &lastModule):
    //    undefined4 __thiscall (CClientExoApp*, ulong, CExoString*, CExoString*) UN/_005e.cpp:8025.
    //    From here the engine drives itself: LoadModuleFinish broadcasts status 1,
    //    the client answers "sModule.Run", RunModule flips server_mode to 2.
    log("load_save: 9 SendLoadGameRequest(-1, '%s', '%s')", dir.c_str(), last_module.c_str());
    capp = client_app();
    const auto sent = call<int>("client.send_load_game_request", reinterpret_cast<void*>(capp), kVerbatimSlot,
                                reinterpret_cast<void*>(sdir.ptr()), reinterpret_cast<void*>(smodule.ptr()));
    if (!sent) return Result::fail("load_save: SendLoadGameRequest not callable");
    log("load_save: request sent (rc=%d); poll server_mode/loading_module/stats", *sent);

    // 10. Arm the AreaLoaded step. It is not part of the GUI path: the engine
    //     sends that message itself once the load's work counter reaches its
    //     total, and headless it never does. Nothing here waits for it --
    //     step_load_completion() picks the load up on a later frame, from the
    //     client-loop drain, when the engine's own state says it is stuck.
    load_step_ = LoadStep::Armed;
    if (!have("msg.area_loaded"))
        log("load_save: 10 msg.area_loaded unresolved on this build, no AreaLoaded step");
    return Result::success();
}

// Take the main menu off the screen, the way the click the harness never makes
// would have.
//
// The menu-free replay reaches the engine functions CSWGuiSaveLoad::LoadGame
// calls, but not the panel bookkeeping around them. On the GUI path
// CSWGuiMainMenu::OnLoadSaveGame (swguimainmenu.cpp:105-118) retires the menu
// panel the moment Load Game is clicked, by setting its own removal bits. The
// harness never goes through that handler, so CSWGuiManager keeps the panel in
// its list and keeps drawing it: the simulation is in the module while the
// frame still shows New Game / Load Game / Quit.
//
// RemovePanel is used here rather than the flag write, because it is an engine
// call and the flag would be a raw write into a GUI object -- the same choice
// the timer unpause makes. It is what the client's own HideLoadScreen uses on
// its panel (UN/_005f.cpp:1720). It unlists the panel and calls its
// OnPanelRemoved; it does not free it, so the CSWGuiMainMenu object stays
// allocated until the process exits, and StopServices skips its destructor
// because PanelExists is then 0.
bool GameAdapter::retire_main_menu() {
    const std::uintptr_t cint = client_internal();
    const auto menu = rd_ptr(cint, "client.main_menu");
    if (main_menu_pointer_absent(menu)) return true;
    if (!menu) return false;
    if (!have("gui.panel_exists")) {
        log("main menu: gui.panel_exists unresolved; cannot verify menu absence");
        return false;
    }
    const auto mgr = rd_ptr(cint, "client.gui_manager");
    if (!mgr || *mgr == 0) return false;
    // The panel is at +0 of CSWGuiMainMenu (types.h:7385), which is why the
    // phase check already hands this same pointer to PanelExists.
    const auto exists = call<int>("gui.panel_exists", reinterpret_cast<void*>(*mgr),
                                  reinterpret_cast<void*>(*menu));
    if (!exists) return false;
    if (*exists == 0) return true;
    if (!have("gui.remove_panel")) {
        log("main menu: gui.remove_panel unresolved; panel remains listed");
        return false;
    }
    const auto rc = call<int>("gui.remove_panel", reinterpret_cast<void*>(*mgr),
                              reinterpret_cast<void*>(*menu));
    const auto after = call<int>("gui.panel_exists", reinterpret_cast<void*>(*mgr),
                                 reinterpret_cast<void*>(*menu));
    log("main menu: RemovePanel(mgr=%08x, panel=%08x) rc=%d, PanelExists now %d",
        static_cast<unsigned>(*mgr), static_cast<unsigned>(*menu), rc.value_or(-1),
        after.value_or(-1));
    return after && *after == 0;
}

// ------------------------------------------- the AreaLoaded step -----------
//
// One message, sent once, to break the load deadlock this harness path creates.
//
// The chain that stalls (measured live, docs/harness-research/
// fill-client-load-completion.md): the client cannot clear
// area_not_ready_to_display without a control object; the ControlObject update
// comes from MovePlayerToArea; MovePlayerToArea runs for a player whose
// CSWSPlayer+0x24 is 2; +0x24 becomes 2 on a PlayerToServer Area/AreaLoaded;
// and the client only sends that from HandleServerToPlayerUpdate_WorkRemaining
// (nwchandlemessage.cpp:1553) when progress reaches total, which needs a
// GameObjUpdate the server never sends because UpdateClientGameObjectsForPlayer
// returns early for an unplaced player. Sending the message ourselves enters
// that ring at the one point the engine leaves open.
//
// What this skips is the readiness accounting only: the load bar never reaches
// 100 percent. Everything after the message is the engine's own sequence, the
// client's completion block included, so the timer unpause and the load-screen
// teardown still happen where they always did -- this route feeds gate 2, it
// does not bypass the block.
void GameAdapter::step_load_completion() {
    if (load_step_ != LoadStep::Armed && load_step_ != LoadStep::Sent &&
        load_step_ != LoadStep::Placed)
        return;

    const std::uintptr_t cint = client_internal();
    const std::uintptr_t sint = server_internal();
    const int server_mode = rd(sint, "server.server_mode").value_or(-1);
    const int not_ready   = rd(cint, "client.area_not_ready_to_display").value_or(-1);
    const int pcid        = rd(cint, "client.player_creature_id").value_or(-1);
    const int continue_message_processing =
        rd(stats(), "stats.continue_message_processing").value_or(-1);
    // load_from_savegame is the proof the route took: MovePlayerToArea is the
    // only site that clears it (serverexoappinternal.cpp:1781).
    const int from_save = rd(sint, "server.load_from_savegame").value_or(-1);

    // Two halves, and they land frames apart, so they are logged apart. The
    // server half is load_from_savegame going 1 -> 0: MovePlayerToArea is the
    // only site that clears it. The client half is player_creature_id leaving
    // OBJECT_INVALID, which is the ControlObject arriving, and after it the
    // completion block clears area_not_ready_to_display itself.
    if (load_step_ == LoadStep::Sent) {
        if (from_save == 0 || pcid != kInvalidObjectId) {
            log("load step: the server placed the player -- load_from_savegame=%d, "
                "player_creature_id=%08x, area_not_ready=%d",
                from_save, static_cast<unsigned>(pcid), not_ready);
            load_step_ = LoadStep::Placed;
            load_placed_at_ = std::chrono::steady_clock::now();
            load_control_fallback_sent_ = false;
            return;
        }
        // Seconds, not frames: the message goes out over the loopback net layer
        // and the server answers on one of its own ticks, and a frame during
        // this load takes anywhere from 8 to 30 seconds under llvmpipe. One
        // shot only -- a resend loop would put the same message on the wire
        // every frame.
        if (std::chrono::steady_clock::now() - load_sent_at_ > std::chrono::seconds(20)) {
            log("load step: AreaLoaded did not take -- 20s on, player_creature_id=%08x, "
                "load_from_savegame=%d, area_not_ready=%d, server_mode=%d",
                static_cast<unsigned>(pcid), from_save, not_ready, server_mode);
            load_step_ = LoadStep::GaveUp;
        }
        return;
    }

    // Nothing is sent from here on. This half only watches, so the log carries
    // the client's side of the handover rather than the driver having to infer
    // it from a phase poll.
    // area_not_ready_to_display going 0 is the completion signal, not the
    // control object: clientexoappinternal.cpp:10988 is the only site that
    // clears it, so a 0 here means the client ran its own completion block.
    // player_creature_id is logged beside it rather than tested, because it
    // was still reading 0x7f000000 at this point on a load that completed
    // (run 20260909-091519) and that is a question about the field, not a
    // reason to call a finished load unfinished.
    if (load_step_ == LoadStep::Placed) {
        if (not_ready == 0) {
            log("load step: the client finished the load -- area_not_ready=%d, "
                "player_creature_id=%08x", not_ready, static_cast<unsigned>(pcid));
            load_step_ = retire_main_menu() ? LoadStep::Done : LoadStep::GaveUp;
        } else if (!load_control_fallback_sent_ && from_save == 0 &&
                   pcid == kInvalidObjectId && server_mode == 2 &&
                   continue_message_processing == 0 &&
                   std::chrono::steady_clock::now() - load_placed_at_ >= std::chrono::seconds(2)) {
            // MainLoop is the engine's only caller of this method, and it
            // makes the same two checks before dispatching GameObjUpdate and
            // ObjControl.  Give that native tick a chance first; this is a
            // one-shot fallback only when its control packet still has not
            // reached the client.
            if (have("app.update_client_game_objects") && sint != 0) {
                callv("app.update_client_game_objects", reinterpret_cast<void*>(sint), 1);
                log("load step: native control update did not arrive; requested one "
                    "scheduled GameObjUpdate/ObjControl delivery");
            } else {
                log("load step: native control update did not arrive and "
                    "app.update_client_game_objects is unresolved");
            }
            load_control_fallback_sent_ = true;
        } else if (std::chrono::steady_clock::now() - load_sent_at_ > std::chrono::seconds(300)) {
            log("load step: the player was placed but the area never became ready -- "
                "area_not_ready=%d, player_creature_id=%08x, continue_message_processing=%d",
                not_ready, static_cast<unsigned>(pcid), continue_message_processing);
            load_step_ = LoadStep::GaveUp;
        }
        return;
    }

    // GetModule is the server's own answer to "is a module loaded"
    // (UN/_004a.cpp:6788, null before LoadModule finishes).
    bool module_ready = false;
    if (const std::uintptr_t sapp = server_app(); sapp != 0 && have("app.get_module"))
        module_ready = call<std::uintptr_t>("app.get_module", reinterpret_cast<void*>(sapp)).value_or(0) != 0;
    if (normal_load_completed(load_from_save_observed_,
                              sint != 0 && sint == load_server_internal_,
                              server_mode, module_ready, not_ready, from_save)) {
        log("load step: native load completed normally; retiring main menu");
        // One attempt per issued load, including an unresolved/failed panel call.
        // A failed absence check is terminal uncertainty, never a claimed Done.
        load_step_ = retire_main_menu() ? LoadStep::Done : LoadStep::GaveUp;
        return;
    }
    if (!area_loaded_due(server_mode, not_ready, pcid, module_ready)) return;

    if (!have("msg.area_loaded")) {
        log("load step: the load is stuck with no control object and msg.area_loaded "
            "is unresolved on this build");
        load_step_ = LoadStep::GaveUp;
        return;
    }
    const Bound* b = find("msg.area_loaded");
    log("load step: stuck load -- server_mode=%d area_not_ready=%d player_creature_id=%08x "
        "load_from_savegame=%d; sending PlayerToServer Area/AreaLoaded",
        server_mode, not_ready, static_cast<unsigned>(pcid), from_save);
    {
        HookBodyScope scope;
        const auto rc = call_static<int>(shape_, b->addr);
        log("load step: AreaLoaded call returned %d", rc);
    }
    load_sent_at_ = std::chrono::steady_clock::now();
    load_step_ = LoadStep::Sent;
}

Result GameAdapter::new_game() {
    // This is the exact first GUI transition, not a synthetic "start game":
    // CSWGuiMainMenu::OnNewGamePicked constructs CSWGuiClassSelection for
    // END_M01AA and adds it to the live manager (swguimainmenu.cpp:612-639).
    // The following character-generation panels remain engine-owned too.
    const Result req = require({"client.main_menu", "client.gui_manager", "gui.panel_exists",
                                "gui.main_menu_new_game", "menu.newgame_button", "menu.ready",
                                "gui.panel_bit_flags", "gui.control_active", "gui.panels_data", "gui.panels_size"});
    if (!req.ok) return req;
    const std::uintptr_t cint = client_internal();
    const auto mgr = rd_ptr(cint, "client.gui_manager");
    const auto menu = rd_ptr(cint, "client.main_menu");
    if (!mgr || *mgr == 0 || !menu || *menu == 0) return Result::fail("new_game: main menu is not live");
    const auto menu_exists = call<int>("gui.panel_exists", reinterpret_cast<void*>(*mgr),
                                       reinterpret_cast<void*>(*menu));
    if (!menu_exists || *menu_exists == 0) return Result::fail("new_game: main menu is not listed");
    if (new_game_panel_ != 0) {
        const auto open = call<int>("gui.panel_exists", reinterpret_cast<void*>(*mgr),
                                    reinterpret_cast<void*>(new_game_panel_));
        if (open && *open != 0) return Result::fail("new_game: character generation is already open");
        new_game_panel_ = 0;
    }
    main_char_gen_panel_ = 0;
    chargen_stage_ = ChargenStage::None;

    const std::vector<std::uintptr_t> before = gui_panels(*mgr);
    if (before.empty()) return Result::fail("new_game: GUI panel list is unreadable");
    const auto button = at_offset(*menu, off("menu.newgame_button", -1));
    if (!button || !readable(*button, 1)) return Result::fail("new_game: new-game control is unreadable");
    const int flags = rd(*menu, "gui.panel_bit_flags").value_or(-1);
    const int ready = rd(*menu, "menu.ready").value_or(-1);
    const int active = rd(*button, "gui.control_active").value_or(-1);
    if ((flags & 0x600) == 0x400 || ready == 0 || active == 0) {
        return Result::fail("new_game: GUI callback is gated (panel_flags=" + std::to_string(flags) +
                            ", menu_ready=" + std::to_string(ready) +
                            ", control_active=" + std::to_string(active) + ")");
    }
    if (!callv("gui.main_menu_new_game", reinterpret_cast<void*>(*menu), reinterpret_cast<void*>(*button)))
        return Result::fail("new_game: OnNewGamePicked was not callable");
    const std::vector<std::uintptr_t> after = gui_panels(*mgr);
    std::vector<std::uintptr_t> added;
    for (const std::uintptr_t p : after)
        if (std::find(before.begin(), before.end(), p) == before.end()) added.push_back(p);
    if (added.size() != 1 || added.front() == 0)
        return Result::fail("new_game: expected exactly one class-selection panel");
    const auto open = call<int>("gui.panel_exists", reinterpret_cast<void*>(*mgr),
                                reinterpret_cast<void*>(added.front()));
    if (!open || *open == 0) return Result::fail("new_game: added panel is not listed");
    new_game_panel_ = added.front();
    chargen_stage_ = ChargenStage::Class;
    log("new_game: OnNewGamePicked added class-selection panel %08x",
        static_cast<unsigned>(new_game_panel_));
    return Result::success();
}

Result GameAdapter::chargen_select_class(int index) {
    if (index < 0 || index > 5) return Result::fail("chargen_select_class: index must be 0..5");
    const Result req = require({"client.gui_manager", "gui.panel_exists", "gui.class_selection_select_button",
                                "chargen.class_controls", "chargen.class_control", "chargen.main_route_panel",
        "gui.main_chargen_begin_play",
                                "gui.control_active"});
    if (!req.ok) return req;
    if (new_game_panel_ == 0 || chargen_stage_ != ChargenStage::Class)
        return Result::fail("chargen_select_class: class selection is not open");
    const auto mgr = rd_ptr(client_internal(), "client.gui_manager");
    if (!mgr || *mgr == 0) return Result::fail("chargen_select_class: GUI manager is not live");
    const auto listed = call<int>("gui.panel_exists", reinterpret_cast<void*>(*mgr),
                                  reinterpret_cast<void*>(new_game_panel_));
    if (!listed || *listed == 0) {
        new_game_panel_ = 0;
        chargen_stage_ = ChargenStage::None;
        return Result::fail("chargen_select_class: class selection is not listed");
    }
    const auto controls = at_offset(new_game_panel_, off("chargen.class_controls", -1));
    const auto control = controls ? at_index(*controls, index, stride("chargen.class_control", -1))
                                  : std::nullopt;
    if (!control || !readable(*control, 1))
        return Result::fail("chargen_select_class: class control is unreadable");
    const int active = rd(*control, "gui.control_active").value_or(-1);
    if (active <= 0) return Result::fail("chargen_select_class: class control is inactive");
    const std::vector<std::uintptr_t> before = gui_panels(*mgr);
    if (before.empty()) return Result::fail("chargen_select_class: GUI panel list is unreadable");
    if (!callv("gui.class_selection_select_button", reinterpret_cast<void*>(new_game_panel_),
               reinterpret_cast<void*>(*control)))
        return Result::fail("chargen_select_class: OnSelectButton was not callable");
    // OnSelectButton adds CSWGuiMainCharGen.  AddPanel synchronously invokes
    // its OnPanelAdded, which adds the initial child panel as well.  The class
    // selection stays listed, so this transition has precisely two new
    // manager-owned panels.  CSWGuiManager's array ordering is an implementation
    // detail, however: prove the pair through MainCharGen::route_panel rather
    // than treating callback order as list order.
    const std::vector<std::uintptr_t> after = gui_panels(*mgr);
    std::vector<std::uintptr_t> added;
    for (const std::uintptr_t panel : after)
        if (std::find(before.begin(), before.end(), panel) == before.end()) added.push_back(panel);
    const bool class_still_listed = panel_is_listed(*mgr, new_game_panel_);
    std::vector<std::uintptr_t> route_values;
    route_values.reserve(std::min<std::size_t>(added.size(), 4));
    for (std::size_t i = 0; i < added.size() && i < 4; ++i) {
        const auto route = at_offset(added[i], off("chargen.main_route_panel", -1));
        route_values.push_back(route ? read_ptr(*route).value_or(0) : 0);
    }
    const ChargenPanelPair linked = classify_chargen_panel_pair(added, route_values);
    const bool first_listed = added.size() > 0 && panel_is_listed(*mgr, added[0]);
    const bool second_listed = added.size() > 1 && panel_is_listed(*mgr, added[1]);
    const bool additions_live = static_cast<bool>(linked) && first_listed && second_listed;
    if (!class_still_listed || !additions_live) {
        // Bound this failure evidence to the manager delta and the one field
        // source identifies as the parent/child link.  This never scans panel
        // memory or guesses types from a vtable.
        std::string detail = "before_count=" + std::to_string(before.size()) +
                             ", after_count=" + std::to_string(after.size()) +
                             ", class_listed=" + std::to_string(class_still_listed) +
                             ", added=";
        for (std::size_t i = 0; i < added.size() && i < 4; ++i) {
            char item[96];
            std::snprintf(item, sizeof item, "%s%08x(listed=%d,route=%08x)",
                          i == 0 ? "" : ";", static_cast<unsigned>(added[i]),
                          i == 0 ? first_listed : (i == 1 ? second_listed : panel_is_listed(*mgr, added[i])),
                          static_cast<unsigned>(route_values[i]));
            detail += item;
        }
        log("chargen_select_class: structural failure: %s", detail.c_str());
        new_game_panel_ = 0;
        main_char_gen_panel_ = 0;
        chargen_stage_ = ChargenStage::None;
        return Result::fail("chargen_select_class: expected live class selection plus linked main character-generation panel and child (" + detail + ")");
    }
    main_char_gen_panel_ = linked.main;
    chargen_stage_ = ChargenStage::Route;
    log("chargen_select_class: OnSelectButton(%d)", index);
    return Result::success();
}

Result GameAdapter::chargen_begin_play() {
    // CSWGuiMainCharGen::BeginPlayGame is the native end of character
    // generation: it removes chargen panels, saves the generated creature,
    // creates the server, connects, and issues the Module.Load command.  Do
    // not reproduce those internals or synthesize TEMP: files here.
    const Result req = require({"client.gui_manager", "gui.panel_exists",
                                "chargen.main_route_panel", "chargen.main_quick_panel",
                                "chargen.child_main_panel", "chargen.main_visible_panel",
                                "gui.main_chargen_set_visible_panel", "gui.main_chargen_begin_play"});
    if (!req.ok) return req;
    if (main_char_gen_panel_ == 0 || chargen_stage_ != ChargenStage::Route)
        return Result::fail("chargen_begin_play: main character-generation route is not open");
    const auto mgr = rd_ptr(client_internal(), "client.gui_manager");
    if (!mgr || *mgr == 0 || !panel_is_listed(*mgr, main_char_gen_panel_)) {
        main_char_gen_panel_ = 0;
        chargen_stage_ = ChargenStage::None;
        return Result::fail("chargen_begin_play: main character-generation route is not listed");
    }

    const auto route = rd_ptr(main_char_gen_panel_, "chargen.main_route_panel");
    const auto quick = rd_ptr(main_char_gen_panel_, "chargen.main_quick_panel");
    const auto route_parent = route && *route != 0
        ? rd_ptr(*route, "chargen.child_main_panel") : std::nullopt;
    const auto quick_parent = quick && *quick != 0
        ? rd_ptr(*quick, "chargen.child_main_panel") : std::nullopt;
    if (!route || *route == 0 || !route_parent || *route_parent != main_char_gen_panel_ ||
        !panel_is_listed(*mgr, *route))
        return Result::fail("chargen_begin_play: current route child is not live or owned by the main panel");
    if (!quick || *quick == 0 || !quick_parent || *quick_parent != main_char_gen_panel_)
        return Result::fail("chargen_begin_play: QuickPanel is not valid or owned by the main panel");

    // The quick-character button's normal route performs this transition
    // after class selection and before BeginPlayGame. It initializes the
    // class-granted feats and the remaining generated-creature state.
    if (!callv("gui.main_chargen_set_visible_panel",
               reinterpret_cast<void*>(main_char_gen_panel_), 2))
        return Result::fail("chargen_begin_play: SetVisiblePanel(main, 2) was not callable");
    const auto visible = rd(main_char_gen_panel_, "chargen.main_visible_panel");
    if (!visible || *visible != 2 || !panel_is_listed(*mgr, *quick))
        return Result::fail("chargen_begin_play: native quick-character initialization did not expose QuickPanel 2");

    if (!callv("gui.main_chargen_begin_play", reinterpret_cast<void*>(main_char_gen_panel_)))
        return Result::fail("chargen_begin_play: BeginPlayGame was not callable");
    // BeginPlayGame synchronously removes its panels then starts an asynchronous
    // engine load.  The driver proves actual fresh gameplay through the normal
    // phase/module/PC predicates; never claim completion from this callback.
    new_game_panel_ = 0;
    main_char_gen_panel_ = 0;
    chargen_stage_ = ChargenStage::None;
    log("chargen_begin_play: engine BeginPlayGame issued");
    return Result::success();
}

std::string GameAdapter::chargen_stage() {
    const auto mgr = rd_ptr(client_internal(), "client.gui_manager");
    const std::uintptr_t panel = chargen_stage_ == ChargenStage::Class ? new_game_panel_
                               : chargen_stage_ == ChargenStage::Route ? main_char_gen_panel_ : 0;
    if (chargen_stage_ != ChargenStage::None && (!mgr || *mgr == 0 || !panel_is_listed(*mgr, panel))) {
        new_game_panel_ = 0;
        main_char_gen_panel_ = 0;
        chargen_stage_ = ChargenStage::None;
    }
    switch (chargen_stage_) {
    case ChargenStage::Class: return "class";
    case ChargenStage::Route: return "route";
    default: return "none";
    }
}

bool GameAdapter::panel_is_listed(std::uintptr_t manager, std::uintptr_t panel) const {
    if (manager == 0 || panel == 0) return false;
    const auto listed = call<int>("gui.panel_exists", reinterpret_cast<void*>(manager),
                                  reinterpret_cast<void*>(panel));
    return listed && *listed != 0;
}

std::vector<std::uintptr_t> GameAdapter::gui_panels(std::uintptr_t manager) const {
    if (manager == 0) return {};
    const auto data = rd_ptr(manager, "gui.panels_data");
    const auto count = rd(manager, "gui.panels_size");
    if (!data || *data == 0 || !count || *count <= 0 || *count > 128) return {};
    std::vector<std::uintptr_t> panels;
    panels.reserve(static_cast<std::size_t>(*count));
    for (int i = 0; i < *count; ++i) {
        const auto at = at_index(*data, i, sizeof(std::uintptr_t));
        if (!at) return {};
        const auto panel = read_ptr(*at);
        if (!panel) return {};
        panels.push_back(*panel);
    }
    return panels;
}

Result GameAdapter::save(int slot, const std::string& name) {
    if (slot < 0 || name.empty()) return Result::fail("save: slot >= 0 and a name are required");
    const Result req = require({"g.app_manager", "client.send_save_game_request"});
    if (!req.ok) return req;
    const std::uintptr_t capp = client_app();
    if (capp == 0 || server_app() == 0) return Result::fail("save: no server");
    // SendSaveGameRequest(client, slot, &dirName, &displayName):
    // undefined4 __thiscall (CClientExoApp*, ulong, CExoString*, CExoString*) UN/_005e.cpp:8006.
    // The server forms 'SAVES:%06d - %s' from slot and dirName and runs the
    // whole save in one server tick (StallEventSaveGame); completion is the
    // driver's to poll: stats.phase 2 seen, then continue_message_processing 0,
    // then SAVEGAME.sav newer than the request.
    OwnedExoString sname(name);
    log("save: SendSaveGameRequest(%d, '%s', '%s')", slot, name.c_str(), name.c_str());
    const auto rc = call<int>("client.send_save_game_request", reinterpret_cast<void*>(capp),
                              static_cast<std::uint32_t>(slot), reinterpret_cast<void*>(sname.ptr()),
                              reinterpret_cast<void*>(sname.ptr()));
    if (!rc) return Result::fail("save: SendSaveGameRequest not callable");
    return Result::success();
}

// ------------------------------------------------------------------ warp ---

Result GameAdapter::warp(const std::string& module) {
    if (module.empty() || module.size() > 16) return Result::fail("warp: module must be a resref");
    const Result req = require({"g.app_manager", "app.set_move_to_module_pending",
                                "app.set_move_to_module_string",
                                "app.set_move_to_module_start_waypoint"});
    if (!req.ok) return req;
    const std::uintptr_t sapp = server_app();
    if (sapp == 0) return Result::fail("warp: no server");
    // Exactly what ExecuteCommandStartNewModule does (nwvmachinecommands.cpp:
    // 20932-20953) minus the fade: the string and waypoint through their
    // setters (UN/_004a.cpp:7946, :8006, both take CExoString*), pending last
    // (:7931). The server loop consumes it on its next tick; the only gate,
    // CGuiInGame+0xdc, is dead on every PC build.
    OwnedExoString smod(module);
    OwnedExoString sway("");
    callv("app.set_move_to_module_string", reinterpret_cast<void*>(sapp), reinterpret_cast<void*>(smod.ptr()));
    callv("app.set_move_to_module_start_waypoint", reinterpret_cast<void*>(sapp),
          reinterpret_cast<void*>(sway.ptr()));
    callv("app.set_move_to_module_pending", reinterpret_cast<void*>(sapp), 1);
    log("warp: move to '%s' pending", module.c_str());
    return Result::success();
}

// ---------------------------------------------------------------- dialog ---

std::uintptr_t GameAdapter::as_sws_object(std::uintptr_t obj, std::string* why) const {
    // CGameObject vtable slot AsSWSObject (types.h:13190, slot 4), thiscall, returns CSWSObject*.
    const int slot = lay_.gameobject_as_sws_slot;
    const auto vt = read_ptr(obj);
    const auto slot_at = vt ? at_index(*vt, slot, 4) : std::nullopt;
    const auto fn = slot_at ? read_ptr(*slot_at) : std::nullopt;
    if (!fn || *fn == 0 || !readable(*fn, 1)) { *why = "owner vtable not readable"; return 0; }
    std::uintptr_t sws = 0;
    {
        HookBodyScope scope;
        sws = call_this<std::uintptr_t>(shape_, *fn, reinterpret_cast<void*>(obj));
    }
    if (sws == 0) *why = "owner is not a CSWSObject";
    return sws;
}

std::optional<GameAdapter::ServerDialog> GameAdapter::server_dialog(std::uintptr_t panel, std::string* why) const {
    const std::uintptr_t sapp = server_app();
    if (sapp == 0) { *why = "no server"; return std::nullopt; }
    const auto owner_cid = rd(panel, "gui.dialog_owner");
    if (!owner_cid) { *why = "gui.dialog_owner not readable"; return std::nullopt; }
    // ClientToServerObjectId(server, id): ulong __thiscall UN/_004a.cpp:7597
    const auto sid = call<std::uint32_t>("server.client_to_server_object_id", reinterpret_cast<void*>(sapp),
                                         static_cast<std::uint32_t>(*owner_cid));
    if (!sid) { *why = "server.client_to_server_object_id unresolved"; return std::nullopt; }
    // GetGameObject(server, id): CGameObject* __thiscall UN/_004a.cpp:6859
    const auto obj = call<std::uintptr_t>("server.get_game_object", reinterpret_cast<void*>(sapp), *sid);
    if (!obj || *obj == 0) { *why = "dialog owner has no game object"; return std::nullopt; }
    const std::uintptr_t sws = as_sws_object(*obj, why);
    if (sws == 0) return std::nullopt;
    const auto dlg = rd_ptr(sws, "object.dialog_ptr");
    if (!dlg) { *why = "object.dialog_ptr not readable"; return std::nullopt; }
    return ServerDialog{sws, *dlg, *sid};
}

Result GameAdapter::dialog(DialogState* out) {
    if (out == nullptr) return Result::fail("dialog: null out");
    *out = DialogState{};
    const Result req = require({"gui.dialog_active", "gui.reply_count", "gui.reply_texts", "gui.reply_links"});
    if (!req.ok) return req;
    const std::uintptr_t gui = gui_in_game();
    if (gui == 0) return Result::fail("dialog: CGuiInGame not reachable (client.gui_in_game / client.get_in_game_gui)");

    const auto active = rd(gui, "gui.dialog_active");
    if (!active) return Result::fail("dialog: gui.dialog_active not readable");
    out->active = *active != 0;
    if (!out->active) return Result::success();

    const int count = rd(gui, "gui.reply_count").value_or(0);
    const auto texts = rd_ptr(gui, "gui.reply_texts");
    const auto links = rd_ptr(gui, "gui.reply_links");
    const auto pending_at = at_offset(gui, off("gui.dialog_pending", lay_.gui_selection_pending));
    const int pending = pending_at ? read_int(*pending_at, 4).value_or(-1) : -1;

    // Active rows come first in the client's table and greyed
    // (display_inactive) rows are appended after them, so only the inactive
    // count separates the two (nwsdialog.cpp:3796-3802, HandleDialogReplies
    // takes activeCount and inactiveCount). The client stores the total alone,
    // and no build read so far carries the split; a table row named
    // gui.reply_inactive_count supplies it where one does. Without that row
    // every row reports active, which is what the protocol meant all along.
    const auto inactive_at = at_offset(gui, off("gui.reply_inactive_count", -1));
    const int inactive = inactive_at ? read_int(*inactive_at, 4).value_or(0) : 0;
    const int active_rows = (inactive > 0 && inactive <= count) ? count - inactive : count;

    // The client's reply table (CGuiInGame +0x114/+0x118/+0x11c on K1): already
    // TLK-parsed, greyed rows included, max 20 rows shown.
    if (count > 0 && count <= 64 && texts && links) {
        for (int i = 0; i < count; ++i) {
            const auto link_at = at_index(*links, i, 4);
            const auto text_at = at_index(*texts, i, sizeof(CExoString));
            if (!link_at || !text_at) break;
            DialogReply r;
            r.visible_index = i;
            r.link_index = read_int(*link_at, 4).value_or(-1);
            r.text = read_exostring_at(*text_at).value_or(std::string());
            r.active = i < active_rows;
            out->replies.push_back(std::move(r));
        }
    }

    const auto panel_at = at_offset(gui, off("gui.dialog_panel", lay_.gui_dialog_panel));
    const std::uintptr_t panel = panel_at ? read_ptr(*panel_at).value_or(0) : 0;
    const auto entry_at = at_offset(panel, off("dialog.panel_current_entry", lay_.panel_entry));
    const int panel_entry = entry_at ? read_int(*entry_at, 4).value_or(-1) : -1;

    int send_pending = -1;
    std::string why;
    if (panel != 0) {
        if (const auto sd = server_dialog(panel, &why); sd && sd->dialog != 0) {
            out->current_entry = rd(sd->dialog, "dialog.current_entry").value_or(-1);
            out->current_reply = rd(sd->dialog, "dialog.current_reply").value_or(-1);
            send_pending = rd(sd->owner_sws, "object.dialog_send_pending").value_or(-1);
            // Entry text: the node's CExoLocString strref. There is no TLK site,
            // so the driver gets "strref:<n>" and resolves it from dialog.tlk.
            const auto entries = rd_ptr(sd->dialog, "dialog.entries");
            const int estride = stride("dialog.entry", lay_.dialog_entry_stride);
            const int strref_off = off("dialog.node_strref", lay_.dialog_text_strref);
            const auto node = (entries && *entries != 0)
                                  ? at_index(*entries, out->current_entry, estride) : std::nullopt;
            const auto strref_at = node ? at_offset(*node, strref_off) : std::nullopt;
            if (strref_at)
                if (const auto strref = read_int(*strref_at, 4); strref)
                    out->entry_text = "strref:" + std::to_string(*strref);
        }
    }
    out->waiting_for_player = reply_accepted(*active, pending, count, out->current_reply, send_pending,
                                             panel_entry, out->current_entry);
    // The owner is mid-send while the entry's VO or node delay runs
    // (CSWSObject+0x48; owner+0x48 == 1 is "waiting on IsDialogDelay /
    // IsSoundPlayingInDialog", fill-Reply_choice_by_engine_call_t.md). VO waits
    // do not scale with game speed, so this is what tells the driver a
    // dialog_skip is the right move. Any nonzero value is the wait, the way
    // reply_accepted already reads the same field; unknown (-1) is not a wait,
    // because an unreadable owner must not make the driver skip for ever.
    out->waiting_on_sound = out->active && send_pending > 0;
    return Result::success();
}

Result GameAdapter::reply(int visible_index) {
    const Result req = require({"gui.dialog_active", "gui.reply_count", "gui.dialog_owner",
                                "server.client_to_server_object_id", "server.get_game_object",
                                "object.dialog_ptr", "object.dialog_send_pending",
                                "dialog.current_entry", "dialog.current_reply"});
    if (!req.ok) return req;
    const std::uintptr_t gui = gui_in_game();
    if (gui == 0) return Result::fail("reply: CGuiInGame not reachable");
    const auto panel_at = at_offset(gui, off("gui.dialog_panel", lay_.gui_dialog_panel));
    const std::uintptr_t panel = panel_at ? read_ptr(*panel_at).value_or(0) : 0;
    if (panel == 0) return Result::fail("reply: no dialog panel");

    const int active = rd(gui, "gui.dialog_active").value_or(-1);
    const int count = rd(gui, "gui.reply_count").value_or(-1);
    const auto pending_at = at_offset(gui, off("gui.dialog_pending", lay_.gui_selection_pending));
    const int pending = pending_at ? read_int(*pending_at, 4).value_or(-1) : -1;
    const auto entry_at = at_offset(panel, off("dialog.panel_current_entry", lay_.panel_entry));
    const int panel_entry = entry_at ? read_int(*entry_at, 4).value_or(-1) : -1;
    const auto visible_at = at_offset(panel, off("dialog.panel_visible_count", lay_.panel_visible_count));
    const int visible = visible_at ? read_int(*visible_at, 4).value_or(count) : count;

    std::string why;
    const auto sd = server_dialog(panel, &why);
    if (!sd) return Result::fail("reply: " + why);
    if (sd->dialog == 0) return Result::fail("reply: owner has no CSWSDialog");
    const int server_entry = rd(sd->dialog, "dialog.current_entry").value_or(-1);
    const int server_reply = rd(sd->dialog, "dialog.current_reply").value_or(-2);
    const int send_pending = rd(sd->owner_sws, "object.dialog_send_pending").value_or(-1);

    if (!reply_accepted(active, pending, count, server_reply, send_pending, panel_entry, server_entry)) {
        char buf[200];
        std::snprintf(buf, sizeof buf,
                      "reply: not accepted (active=%d pending=%d count=%d server_reply=%d send_pending=%d "
                      "panel_entry=%d server_entry=%d)",
                      active, pending, count, server_reply, send_pending, panel_entry, server_entry);
        return Result::fail(buf);
    }
    if (visible_index < 0 || visible_index >= count || visible_index >= visible)
        return Result::fail("reply: visible index out of range");

    // CSWGuiDialog::SelectReply(visibleIdx) through the panel's vtable slot
    // (swguidialog.cpp:335), so the computer-terminal and cinematic variants
    // are covered; the base address (dialog.select_reply) is the fallback
    // when the vtable cannot be read. It refuses idx >= count with 0, else
    // SetDialogSelection + UpdateDialog -> ReplyDialog(..., fromClient=1)
    // synchronously.
    const auto vt = read_ptr(panel);
    const auto slot_at = vt ? at_index(*vt, lay_.panel_select_reply_slot, 4) : std::nullopt;
    const auto fn = slot_at ? read_ptr(*slot_at) : std::nullopt;
    int rc = 0;
    if (fn && *fn != 0 && readable(*fn, 1)) {
        HookBodyScope scope;
        rc = call_this<int, int>(shape_, *fn, reinterpret_cast<void*>(panel), visible_index);
    } else if (const auto r = call<int, int>("dialog.select_reply", reinterpret_cast<void*>(panel), visible_index); r) {
        rc = *r;
    } else {
        return Result::fail("reply: panel vtable not readable and dialog.select_reply unresolved");
    }
    log("reply: SelectReply(%d) -> %d", visible_index, rc);
    if (rc == 0) return Result::fail("reply: SelectReply refused the index");
    return Result::success();
}

Result GameAdapter::dialog_continue() {
    const Result req = require({"gui.dialog_active", "gui.reply_count", "gui.reply_texts", "gui.reply_links",
                                "gui.dialog_owner", "server.client_to_server_object_id", "server.get_game_object",
                                "object.dialog_ptr", "dialog.current_entry", "dialog.current_reply",
                                "gui.set_dialog_selection", "gui.update_dialog"});
    if (!req.ok) return req;
    DialogState ds;
    const Result dr = dialog(&ds);
    if (!dr.ok) return dr;
    if (!ds.active || ds.replies.size() != 1 || !ds.replies[0].active || !ds.replies[0].text.empty())
        return Result::fail("dialog_continue: requires exactly one active empty reply");
    if (ds.current_entry < 0 || ds.current_reply != -1 || ds.waiting_for_player)
        return Result::fail("dialog_continue: dialog is not an entry continuation");
    const std::uintptr_t gui = gui_in_game();
    if (gui == 0) return Result::fail("dialog_continue: CGuiInGame not reachable");
    const int count = rd(gui, "gui.reply_count").value_or(-1);
    if (count != 1) return Result::fail("dialog_continue: reply table changed");
    // SetDialogSelection(gui, index, count, isReply=0) is the native
    // empty-reply continuation path; UpdateDialog consumes it synchronously.
    callv("gui.set_dialog_selection", reinterpret_cast<void*>(gui), 0, count, 0);
    callv("gui.update_dialog", reinterpret_cast<void*>(gui));
    log("dialog_continue: consumed empty reply at entry %d", ds.current_entry);
    return Result::success();
}

Result GameAdapter::dialog_skip() {
    const Result req = require({"g.app_manager", "dialog.skip_past", "gui.dialog_owner",
                                "server.client_to_server_object_id", "server.get_game_object",
                                "object.dialog_ptr"});
    if (!req.ok) return req;
    const std::uintptr_t gui = gui_in_game();
    const auto panel_at = at_offset(gui, off("gui.dialog_panel", lay_.gui_dialog_panel));
    const std::uintptr_t panel = panel_at ? read_ptr(*panel_at).value_or(0) : 0;
    if (panel == 0) return Result::fail("dialog_skip: no dialog panel");
    std::string why;
    const auto sd = server_dialog(panel, &why);
    if (!sd) return Result::fail("dialog_skip: " + why);
    // CServerExoApp::SkipPastDialog(this, ulong ownerId): UN/_004a.cpp:7396. Sets
    // the owner's skip-requested flag; honoured by IsDialogDelay only when the
    // DLG is Skippable, and it is what the Escape key does.
    //
    // A forced CSWSDialog::Skippable write here (field_3c, offset 0x3c) was
    // tried to push past a textless VO node that hangs forever on
    // waiting_on_sound in this headless/muted environment. It did make
    // IsDialogDelay honour the skip (confirmed live, zero dialog_abort
    // fallbacks needed) and the party did reach its authored destination, but
    // a save taken afterward was reproducibly corrupted ("ERF member '' has
    // unmapped restype 0xffff") -- including a save taken well before that
    // specific stall, meaning the corruption is not confined to the one
    // conversation it targeted. Reverted for safety until root-caused; do not
    // reintroduce a raw struct write here without first proving a save taken
    // after it is not corrupted.
    callv("dialog.skip_past", reinterpret_cast<void*>(server_app()), sd->owner_sid);
    return Result::success();
}

Result GameAdapter::dialog_abort() {
    const std::uintptr_t gui = gui_in_game();
    if (gui == 0) return Result::fail("dialog_abort: CGuiInGame not reachable");
    if (rd(gui, "gui.dialog_active").value_or(0) == 0) return Result::fail("dialog_abort: no conversation");
    // Never SetDialogSelection(-3, ...): UpdateDialog indexes the reply arrays
    // before it looks at the sentinel (RE audit 2). HandleDialogSelection(gui,
    // -2, n) returns to CloseDialog before any array read (guiingame.cpp:5989,
    // 6021-6026); StopDialog(owner) is the server-side fallback.
    if (have("gui.handle_dialog_selection")) {
        const int count = rd(gui, "gui.reply_count").value_or(0);
        callv("gui.handle_dialog_selection", reinterpret_cast<void*>(gui), -2, count);
        return Result::success();
    }
    const Result req = require({"object.stop_dialog", "gui.dialog_owner", "server.client_to_server_object_id",
                                "server.get_game_object", "object.dialog_ptr"});
    if (!req.ok) return req;
    const auto panel_at = at_offset(gui, off("gui.dialog_panel", lay_.gui_dialog_panel));
    const std::uintptr_t panel = panel_at ? read_ptr(*panel_at).value_or(0) : 0;
    if (panel == 0) return Result::fail("dialog_abort: no dialog panel");
    std::string why;
    const auto sd = server_dialog(panel, &why);
    if (!sd) return Result::fail("dialog_abort: " + why);
    // CSWSObject::StopDialog(this): nwsobject.cpp:891.
    callv("object.stop_dialog", reinterpret_cast<void*>(sd->owner_sws));
    return Result::success();
}

Result GameAdapter::dialog_clear_sound_wait() {
    const Result req = require({"gui.dialog_owner", "server.client_to_server_object_id",
                                "server.get_game_object", "object.dialog_ptr",
                                "object.dialog_send_pending"});
    if (!req.ok) return req;
    const std::uintptr_t gui = gui_in_game();
    const auto panel_at = at_offset(gui, off("gui.dialog_panel", lay_.gui_dialog_panel));
    const std::uintptr_t panel = panel_at ? read_ptr(*panel_at).value_or(0) : 0;
    if (panel == 0) return Result::fail("dialog_clear_sound_wait: no dialog panel");
    std::string why;
    const auto sd = server_dialog(panel, &why);
    if (!sd) return Result::fail("dialog_clear_sound_wait: " + why);
    const Bound* b = find("object.dialog_send_pending");
    if (!b || !b->is_field || b->size == 0)
        return Result::fail("dialog_clear_sound_wait: object.dialog_send_pending unresolved");
    const auto addr = at_offset(sd->owner_sws, b->offset);
    if (!addr) return Result::fail("dialog_clear_sound_wait: owner address unreadable");
    const int current = read_int(*addr, b->size).value_or(0);
    if (current == 0) return Result::success();
    if (!write_uint(*addr, 0, b->size, "dialog_clear_sound_wait"))
        return Result::fail("dialog_clear_sound_wait: write failed");
    log("dialog_clear_sound_wait: cleared send_pending %d -> 0 on owner 0x%08X",
        current, static_cast<unsigned>(sd->owner_sws));
    return Result::success();
}

Result GameAdapter::clear_auto_pause() {
    const Result req = require({"g.app_manager", "server.pause_state"});
    if (!req.ok) return req;
    const std::uintptr_t sint = server_internal();
    if (sint == 0) return Result::fail("clear_auto_pause: no server internal");
    const Bound* b = find("server.pause_state");
    if (!b || !b->is_field || b->size == 0)
        return Result::fail("clear_auto_pause: server.pause_state unresolved");
    const auto addr = at_offset(sint, b->offset);
    if (!addr) return Result::fail("clear_auto_pause: pause_state address unreadable");
    const int current = read_int(*addr, b->size).value_or(0);
    if (current != 0) {
        if (!write_uint(*addr, 0, b->size, "clear_auto_pause"))
            return Result::fail("clear_auto_pause: write failed");
        log("clear_auto_pause: cleared pause_state %d -> 0", current);
    }
    // The engine's autopause also pauses both world timers; clearing the byte
    // alone leaves scripts and dialog running but freezes everything
    // time-integrated (movement, combat rounds). Restore them the way the
    // engine's own unpause does.
    return unpause_timers();
}

// ------------------------------------------------------------------ time ---

void GameAdapter::apply_speed() {
    const std::uintptr_t cint = client_internal();
    if (cint == 0) return;
    const float k = g_harness_scale.load(std::memory_order_acquire);
    const float e = g_engine_scale.load(std::memory_order_acquire);
    // Through the trampoline when the site is hooked, so this does not re-enter
    // the detour; through the site itself when it is not.
    if (void* orig = g_orig_set_game_speed.load(std::memory_order_acquire); orig != nullptr) {
        HookBodyScope scope;
        call_this<void, float>(shape_, reinterpret_cast<std::uintptr_t>(orig), reinterpret_cast<void*>(cint), e * k);
        return;
    }
    callv("client.set_game_speed", reinterpret_cast<void*>(cint), e * k);
}

float GameAdapter::speed() const { return g_harness_scale.load(std::memory_order_acquire); }

Result GameAdapter::set_speed(float scale) {
    if (!(scale > 0.0f) || scale > 16.0f) return Result::fail("speed: scale must be in (0, 16]");
    if (!fixed_step_fits(fixed_hz_, scale))
        return Result::fail("speed: scale * 1e6 / hz overflows the fixed-step increment");
    if (g_orig_set_game_speed.load(std::memory_order_acquire) == nullptr && !have("client.set_game_speed"))
        return Result::unsupported("client.set_game_speed");
    g_harness_scale.store(scale, std::memory_order_release);
    apply_speed();
    log("speed: scale=%.3f", static_cast<double>(scale));
    return Result::success();
}

Result GameAdapter::after_frame() {
    // Ahead of the scale check: a scenario that never sets a speed still needs
    // the load step, and the check below returns for exactly that scenario.
    step_load_completion();
    step_auto_levelup();
    step_party_leader();
    step_use_item();
    step_door_security();
    step_equip_item();
    if (g_harness_scale.load(std::memory_order_acquire) == 1.0f) return Result::success();
    apply_speed();
    return Result::success();
}

Result GameAdapter::resolve_player_stats(std::uint32_t* player_id, std::uintptr_t* out_stats) const {
    const Result req = require({"client.get_sw_party", "party.get_player_character",
                                "client_creature.get_server_creature", "object.id", "creature.stats"});
    if (!req.ok) return req;
    const std::uintptr_t capp = client_app();
    const auto party = call<std::uintptr_t>("client.get_sw_party", reinterpret_cast<void*>(capp));
    if (!party || *party == 0) return Result::fail("auto_levelup: client party is unavailable");
    const auto client_creature = call<std::uintptr_t>("party.get_player_character",
                                                       reinterpret_cast<void*>(*party));
    if (!client_creature || *client_creature == 0)
        return Result::fail("auto_levelup: client player creature is unavailable");
    const auto creature = call<std::uintptr_t>("client_creature.get_server_creature",
                                                reinterpret_cast<void*>(*client_creature));
    if (!creature || *creature == 0) return Result::fail("auto_levelup: server creature is unavailable");
    const auto raw_id = rd(*creature, "object.id");
    if (!raw_id) return Result::fail("auto_levelup: server creature id is unreadable");
    const std::uint32_t id = static_cast<std::uint32_t>(*raw_id);
    if (id == 0 || id == 0x7f000000u || id == 0xffffffffu)
        return Result::fail("auto_levelup: server creature has an invalid object id");
    const auto player_stats = rd_ptr(*creature, "creature.stats");
    if (!player_stats || *player_stats == 0)
        return Result::fail("auto_levelup: creature stats are unreadable");
    *player_id = id;
    *out_stats = *player_stats;
    return Result::success();
}

Result GameAdapter::auto_levelup() {
    if (auto_level_.armed || auto_level_.ready) return Result::fail("auto_levelup: one transaction is already pending");
    const Result req = require({"stats.auto_levelup", "stats.get_level", "stats.experience"});
    if (!req.ok) return req;
    std::uint32_t player_id = 0;
    std::uintptr_t player_stats = 0;
    const Result resolved = resolve_player_stats(&player_id, &player_stats);
    if (!resolved.ok) return resolved;
    const auto level = call<int>("stats.get_level", reinterpret_cast<void*>(player_stats), 0);
    const auto xp = rd(player_stats, "stats.experience");
    if (!level || !xp || *level < 0 || *xp < 0) return Result::fail("auto_levelup: level or experience is unreadable");
    auto_level_ = PendingAutoLevel{};
    auto_level_.armed = true;
    auto_level_.frames = 2;
    auto_level_.player_id = player_id;
    auto_level_.stats = player_stats;
    auto_level_.level_before = *level;
    auto_level_.experience = static_cast<std::uint32_t>(*xp);
    return Result::success();
}

void GameAdapter::step_auto_levelup() {
    if (!auto_level_.armed || --auto_level_.frames > 0) return;
    auto finish = [this](Result status) {
        auto_level_.status = std::move(status);
        auto_level_.armed = false;
        auto_level_.ready = true;
    };
    std::uint32_t player_id = 0;
    std::uintptr_t player_stats = 0;
    const Result resolved = resolve_player_stats(&player_id, &player_stats);
    if (!resolved.ok) { finish(resolved); return; }
    if (player_id != auto_level_.player_id || player_stats != auto_level_.stats) {
        finish(Result::fail("auto_levelup: player changed before execution"));
        return;
    }
    callv("stats.auto_levelup", reinterpret_cast<void*>(player_stats), 0);
    const auto level = call<int>("stats.get_level", reinterpret_cast<void*>(player_stats), 0);
    const auto xp = rd(player_stats, "stats.experience");
    if (!level || !xp) { finish(Result::fail("auto_levelup: postcondition state is unreadable")); return; }
    if (*level <= auto_level_.level_before) { finish(Result::fail("auto_levelup: level did not rise")); return; }
    if (static_cast<std::uint32_t>(*xp) != auto_level_.experience) {
        finish(Result::fail("auto_levelup: experience changed"));
        return;
    }
    auto_level_.result.player_id = player_id;
    auto_level_.result.level_before = auto_level_.level_before;
    auto_level_.result.level_after = *level;
    auto_level_.result.experience = auto_level_.experience;
    if (have("stats.can_level_up")) {
        const auto can = call<int>("stats.can_level_up", reinterpret_cast<void*>(player_stats));
        if (!can) { finish(Result::fail("auto_levelup: CanLevelUp result is unreadable")); return; }
        auto_level_.result.can_level_up = *can;
        if (*can != 0) { finish(Result::fail("auto_levelup: player can still level up")); return; }
    }
    finish(Result::success());
}

bool GameAdapter::take_auto_levelup_result(Result* status, AutoLevelResult* out) {
    if (!auto_level_.ready) return false;
    *status = std::move(auto_level_.status);
    *out = auto_level_.result;
    auto_level_ = PendingAutoLevel{};
    return true;
}

Result GameAdapter::set_party_leader(int selector) {
    if (party_leader_.armed || party_leader_.ready)
        return Result::fail("set_party_leader: one transaction is already pending");
    if (selector < 0) return Result::fail("set_party_leader: index must be zero or greater");
    const Result req = require({"client.get_sw_party", "party.get_player_character",
                                "party.set_leader", "client.get_creature_by_object_id",
                                "client_party.count", "client_party.member",
                                "client_party.member_id", "object.id"});
    if (!req.ok) return req;
    const auto party = call<std::uintptr_t>("client.get_sw_party", reinterpret_cast<void*>(client_app()));
    if (!party || *party == 0) return Result::fail("set_party_leader: client party is unavailable");
    const auto count = rd(*party, "client_party.count");
    if (!count || *count < 1 || *count > 3 || selector >= *count)
        return Result::fail("set_party_leader: index is outside the current party");
    const int member_stride = stride("client_party.member", -1);
    const int id_offset = off("client_party.member_id", -1);
    const auto target_at = at_offset(*party, off("client_party.member", -1) +
        static_cast<std::int64_t>(selector) * member_stride + id_offset);
    const auto target_id = target_at ? read_uint(*target_at, 4) : std::nullopt;
    const auto target = target_id ? call<std::uintptr_t>("client.get_creature_by_object_id",
        reinterpret_cast<void*>(client_app()), *target_id) : std::nullopt;
    if (!target_id || !target || *target == 0)
        return Result::fail("set_party_leader: selected party member is unreadable");
    const auto leader = call<std::uintptr_t>("party.get_player_character", reinterpret_cast<void*>(*party));
    const auto id = leader && *leader ? rd(*leader, "object.id") : std::nullopt;
    if (!id) return Result::fail("set_party_leader: current leader is unreadable");
    party_leader_ = PendingPartyLeader{};
    party_leader_.armed = true;
    party_leader_.frames = 2;
    party_leader_.selector = selector;
    party_leader_.party = *party;
    party_leader_.leader_before = static_cast<std::uint32_t>(*id);
    party_leader_.target_id = *target_id;
    party_leader_.target = *target;
    return Result::success();
}

void GameAdapter::step_party_leader() {
    if (!party_leader_.armed || --party_leader_.frames > 0) return;
    auto finish = [this](Result status) {
        party_leader_.status = std::move(status);
        party_leader_.armed = false;
        party_leader_.ready = true;
    };
    const auto party = call<std::uintptr_t>("client.get_sw_party", reinterpret_cast<void*>(client_app()));
    if (!party || *party != party_leader_.party) {
        finish(Result::fail("set_party_leader: party changed before execution"));
        return;
    }
    if (party_leader_.selector != 0)
        callv("party.set_leader", reinterpret_cast<void*>(*party), party_leader_.selector);
    const auto leader = call<std::uintptr_t>("party.get_player_character", reinterpret_cast<void*>(*party));
    const auto id = leader && *leader ? rd(*leader, "object.id") : std::nullopt;
    if (!id) { finish(Result::fail("set_party_leader: resulting leader is unreadable")); return; }
    const std::uint32_t after = static_cast<std::uint32_t>(*id);
    const auto slot0_at = at_offset(*party, off("client_party.member", -1) +
                                    off("client_party.member_id", -1));
    const auto slot0_id = slot0_at ? read_uint(*slot0_at, 4) : std::nullopt;
    if (!slot0_id || *slot0_id != party_leader_.target_id || *leader != party_leader_.target) {
        finish(Result::fail("set_party_leader: selected member did not become slot-0 leader"));
        return;
    }
    party_leader_.result.leader_before = party_leader_.leader_before;
    party_leader_.result.leader_after = after;
    finish(Result::success());
}

bool GameAdapter::take_party_leader_result(Result* status, PartyLeaderResult* out) {
    if (!party_leader_.ready) return false;
    *status = std::move(party_leader_.status);
    *out = party_leader_.result;
    party_leader_ = PendingPartyLeader{};
    return true;
}

Result GameAdapter::use_item(std::uint32_t item_id, std::uint32_t target_id) {
    if (use_item_.armed || use_item_.ready)
        return Result::fail("use_item: one transaction is already pending");
    if (item_id == 0 || item_id == 0x7f000000u || item_id == 0xffffffffu)
        return Result::fail("use_item: item has an invalid object id");
    const Result req = require({"client.get_sw_party", "party.get_player_character",
                                "client.get_creature_by_object_id",
                                "client_creature.party_menu_use_item", "client_party.member",
                                "client_party.member_id"});
    if (!req.ok) return req;
    const std::uintptr_t capp = client_app();
    const auto party = call<std::uintptr_t>("client.get_sw_party", reinterpret_cast<void*>(capp));
    const auto actor = party && *party ? call<std::uintptr_t>("party.get_player_character",
                                                               reinterpret_cast<void*>(*party)) : std::nullopt;
    const auto slot0_at = party && *party ? at_offset(*party, off("client_party.member", -1) +
                                                      off("client_party.member_id", -1))
                                          : std::nullopt;
    const auto actor_raw_id = slot0_at ? read_uint(*slot0_at, 4) : std::nullopt;
    if (!actor || *actor == 0 || !actor_raw_id)
        return Result::fail("use_item: current player creature is unavailable");
    const std::uint32_t actor_id = static_cast<std::uint32_t>(*actor_raw_id);
    const bool self_target = target_id == 0;
    const std::uint32_t wanted_id = target_id;
    if (!self_target && (wanted_id == 0x7f000000u || wanted_id == 0xffffffffu))
        return Result::fail("use_item: target has an invalid object id");
    const auto target = self_target ? actor
        : call<std::uintptr_t>("client.get_creature_by_object_id", reinterpret_cast<void*>(capp), wanted_id);
    if (!target || *target == 0) return Result::fail("use_item: target creature is unavailable");

    use_item_ = PendingUseItem{};
    use_item_.armed = true;
    use_item_.frames = 2;
    use_item_.actor = *actor;
    use_item_.target = *target;
    use_item_.actor_id = actor_id;
    use_item_.item_id = item_id;
    use_item_.target_id = wanted_id; // zero records the validated self-target form
    return Result::success();
}

void GameAdapter::step_use_item() {
    if (!use_item_.armed || --use_item_.frames > 0) return;
    auto finish = [this](Result status) {
        use_item_.status = std::move(status);
        use_item_.armed = false;
        use_item_.ready = true;
    };
    const auto party = call<std::uintptr_t>("client.get_sw_party", reinterpret_cast<void*>(client_app()));
    const auto actor = party && *party ? call<std::uintptr_t>("party.get_player_character",
                                                               reinterpret_cast<void*>(*party)) : std::nullopt;
    const auto slot0_at = party && *party ? at_offset(*party, off("client_party.member", -1) +
                                                      off("client_party.member_id", -1))
                                          : std::nullopt;
    const auto actor_id = slot0_at ? read_uint(*slot0_at, 4) : std::nullopt;
    if (!actor || *actor != use_item_.actor || !actor_id || *actor_id != use_item_.actor_id) {
        finish(Result::fail("use_item: current player changed before execution"));
        return;
    }
    const auto target = use_item_.target_id == 0 ? actor
        : call<std::uintptr_t>("client.get_creature_by_object_id",
            reinterpret_cast<void*>(client_app()), use_item_.target_id);
    if (!target || *target != use_item_.target) {
        finish(Result::fail("use_item: target changed before execution"));
        return;
    }
    callv("client_creature.party_menu_use_item", reinterpret_cast<void*>(*actor),
          use_item_.item_id, reinterpret_cast<void*>(*target));
    use_item_.result.item_id = use_item_.item_id;
    use_item_.result.target_id = use_item_.target_id;
    finish(Result::success());
}

bool GameAdapter::take_use_item_result(Result* status, UseItemResult* out) {
    if (!use_item_.ready) return false;
    *status = std::move(use_item_.status);
    *out = use_item_.result;
    use_item_ = PendingUseItem{};
    return true;
}

Result GameAdapter::equip_item(std::uint32_t item_id, std::uint32_t slot, bool instant) {
    if (equip_item_.armed || equip_item_.ready)
        return Result::fail("equip_item: one transaction is already pending");
    if (std::string_view(name_) != "k1") return Result::unsupported("creature.run_equip");
    if (item_id == 0 || item_id == 0x7f000000u || item_id == 0xffffffffu)
        return Result::fail("equip_item: item has an invalid object id");
    if (slot >= 32) return Result::fail("equip_item: slot index must be between 0 and 31");
    const std::uint32_t slot_mask = std::uint32_t{1} << slot;
    const Result req = require({"client.get_sw_party", "party.get_player_character",
                                "client_creature.get_server_creature", "client_party.member",
                                "client_party.member_id", "object.id", "server.get_item_by_object_id",
                                "item.id", "item.possessor", "creature.run_equip",
                                "creature.inventory", "inventory.get_item_in_slot"});
    if (!req.ok) return req;

    const std::uintptr_t capp = client_app();
    const auto party = call<std::uintptr_t>("client.get_sw_party", reinterpret_cast<void*>(capp));
    const auto leader = party && *party ? call<std::uintptr_t>("party.get_player_character",
                                                               reinterpret_cast<void*>(*party)) : std::nullopt;
    const auto slot0_at = party && *party ? at_offset(*party, off("client_party.member", -1) +
                                                       off("client_party.member_id", -1)) : std::nullopt;
    const auto slot0_id = slot0_at ? read_uint(*slot0_at, 4) : std::nullopt;
    const auto leader_id = leader && *leader ? rd(*leader, "object.id") : std::nullopt;
    if (!party || *party == 0 || !leader || *leader == 0 || !slot0_id || !leader_id ||
        *slot0_id != static_cast<std::uint32_t>(*leader_id))
        return Result::fail("equip_item: current controlled party leader is unavailable");

    const auto actor = call<std::uintptr_t>("client_creature.get_server_creature",
                                             reinterpret_cast<void*>(*leader));
    const auto actor_id = actor && *actor ? rd(*actor, "object.id") : std::nullopt;
    const auto item = call<std::uintptr_t>("server.get_item_by_object_id",
                                            reinterpret_cast<void*>(server_app()), item_id);
    const auto resolved_item_id = item && *item ? rd(*item, "item.id") : std::nullopt;
    const auto possessor = item && *item ? rd(*item, "item.possessor") : std::nullopt;
    if (!actor || *actor == 0 || !actor_id)
        return Result::fail("equip_item: current leader's server creature is unavailable");
    if (!item || *item == 0 || !resolved_item_id || static_cast<std::uint32_t>(*resolved_item_id) != item_id)
        return Result::fail("equip_item: item object is unavailable or changed identity");
    if (!possessor || static_cast<std::uint32_t>(*possessor) != static_cast<std::uint32_t>(*actor_id))
        return Result::fail("equip_item: item does not belong to the current controlled party leader");

    equip_item_ = PendingEquipItem{};
    equip_item_.armed = true;
    equip_item_.frames = 2;
    equip_item_.party = *party;
    equip_item_.actor = *actor;
    equip_item_.item = *item;
    equip_item_.actor_id = static_cast<std::uint32_t>(*actor_id);
    equip_item_.item_id = item_id;
    equip_item_.slot = slot;
    equip_item_.slot_mask = slot_mask;
    equip_item_.instant = instant;
    return Result::success();
}

void GameAdapter::step_equip_item() {
    if (!equip_item_.armed || --equip_item_.frames > 0) return;
    auto finish = [this](Result status) {
        equip_item_.status = std::move(status);
        equip_item_.armed = false;
        equip_item_.ready = true;
    };

    const auto party = call<std::uintptr_t>("client.get_sw_party", reinterpret_cast<void*>(client_app()));
    const auto leader = party && *party ? call<std::uintptr_t>("party.get_player_character",
                                                               reinterpret_cast<void*>(*party)) : std::nullopt;
    const auto slot0_at = party && *party ? at_offset(*party, off("client_party.member", -1) +
                                                       off("client_party.member_id", -1)) : std::nullopt;
    const auto slot0_id = slot0_at ? read_uint(*slot0_at, 4) : std::nullopt;
    const auto leader_id = leader && *leader ? rd(*leader, "object.id") : std::nullopt;
    const auto actor = leader && *leader ? call<std::uintptr_t>("client_creature.get_server_creature",
                                                                reinterpret_cast<void*>(*leader)) : std::nullopt;
    const auto actor_id = actor && *actor ? rd(*actor, "object.id") : std::nullopt;
    if (!party || *party != equip_item_.party || !leader || *leader == 0 || !slot0_id || !leader_id ||
        *slot0_id != static_cast<std::uint32_t>(*leader_id) || !actor || *actor != equip_item_.actor ||
        !actor_id || static_cast<std::uint32_t>(*actor_id) != equip_item_.actor_id) {
        finish(Result::fail("equip_item: current controlled party leader changed before execution"));
        return;
    }

    const auto item = call<std::uintptr_t>("server.get_item_by_object_id",
                                            reinterpret_cast<void*>(server_app()), equip_item_.item_id);
    const auto item_id = item && *item ? rd(*item, "item.id") : std::nullopt;
    const auto possessor = item && *item ? rd(*item, "item.possessor") : std::nullopt;
    if (!item || *item != equip_item_.item || !item_id ||
        static_cast<std::uint32_t>(*item_id) != equip_item_.item_id || !possessor ||
        static_cast<std::uint32_t>(*possessor) != equip_item_.actor_id) {
        finish(Result::fail("equip_item: item changed identity or ownership before execution"));
        return;
    }

    const auto equipped = call<int>("creature.run_equip", reinterpret_cast<void*>(*actor),
                                    equip_item_.item_id, equip_item_.slot_mask,
                                    equip_item_.instant ? 1 : 0);
    if (!equipped || *equipped != 1) {
        finish(Result::fail("equip_item: native RunEquip rejected the request"));
        return;
    }
    const auto inventory = rd_ptr(*actor, "creature.inventory");
    const auto current = inventory && *inventory
        ? call<std::uintptr_t>("inventory.get_item_in_slot", reinterpret_cast<void*>(*inventory),
                               equip_item_.slot_mask)
        : std::nullopt;
    const auto current_id = current && *current ? rd(*current, "item.id") : std::nullopt;
    if (!current || *current == 0 || !current_id) {
        finish(Result::fail("equip_item: equipped slot is unreadable after RunEquip"));
        return;
    }
    equip_item_.result.requested_item_id = equip_item_.item_id;
    equip_item_.result.current_item_id = static_cast<std::uint32_t>(*current_id);
    equip_item_.result.slot = equip_item_.slot;
    finish(Result::success());
}

bool GameAdapter::take_equip_item_result(Result* status, EquipItemResult* out) {
    if (!equip_item_.ready) return false;
    *status = std::move(equip_item_.status);
    *out = equip_item_.result;
    equip_item_ = PendingEquipItem{};
    return true;
}

std::vector<std::uintptr_t> GameAdapter::world_timers() const {
    std::vector<std::uintptr_t> timers;
    const std::uintptr_t capp = client_app();
    const std::uintptr_t sapp = server_app();
    // CClientExoApp::GetWorldTimer (clientexoapp.cpp:116) and
    // CServerExoApp::GetWorldTimer (serverexoapp.cpp:333), the same two objects
    // load_save step 3 pauses.
    if (capp != 0)
        if (const auto t = call<std::uintptr_t>("client.get_world_timer", reinterpret_cast<void*>(capp));
            t && *t != 0) timers.push_back(*t);
    if (sapp != 0)
        if (const auto t = call<std::uintptr_t>("server.get_world_timer", reinterpret_cast<void*>(sapp));
            t && *t != 0) timers.push_back(*t);
    return timers;
}

Result GameAdapter::unpause_timers() {
    const Result req = require({"g.app_manager", "client.get_world_timer", "server.get_world_timer",
                                "timer.unpause_world_timer"});
    if (!req.ok) return req;
    // CWorldTimer::UnpauseWorldTimer (0x4ae030 on K1): it restores the snapshot
    // from the pause timer rather than clearing a byte. A raw write to the
    // paused byte leaves the timer's snapshots where the pause left them, and
    // in testing that wedged the control channel with the process still alive.
    const std::vector<std::uintptr_t> timers = world_timers();
    if (timers.empty()) return Result::fail("unpause_timers: no world timer readable");
    for (const std::uintptr_t t : timers)
        callv("timer.unpause_world_timer", reinterpret_cast<void*>(t));
    const std::uintptr_t capp = client_app();
    // The animation timer is a third CWorldTimer autopause stops; a door
    // whose open animation never completes is what its stall looks like.
    if (capp != 0 && have("client.get_animation_timer"))
        if (const auto t = call<std::uintptr_t>("client.get_animation_timer", reinterpret_cast<void*>(capp));
            t && *t != 0)
            callv("timer.unpause_world_timer", reinterpret_cast<void*>(*t));
    if (capp != 0 && have("client.set_paused_by_combat"))
        callv("client.set_paused_by_combat", reinterpret_cast<void*>(capp), 0, 0, 0);
    if (capp != 0 && have("client.set_auto_paused"))
        callv("client.set_auto_paused", reinterpret_cast<void*>(capp), 0, 0);
    log("unpause_timers: unpaused %zu timer(s), combat=%s auto=%s", timers.size(),
        have("client.set_paused_by_combat") ? "cleared" : "unavailable",
        have("client.set_auto_paused") ? "cleared" : "unavailable");
    return Result::success();
}

Result GameAdapter::advance_tutorial() {
    const Result req = require({"client.gui_manager", "gui.panel_exists", "gui.remove_panel",
                                "gui.tutorial_box", "gui.tutorial_handle_input",
                                "gui.messagebox_callback", "gui.messagebox_callback_context"});
    if (!req.ok) return req;

    const std::uintptr_t gui = gui_in_game();
    const std::uintptr_t cint = client_internal();
    if (gui == 0 || cint == 0) return Result::fail("advance_tutorial: no in-game GUI");

    const auto panel = rd_ptr(gui, "gui.tutorial_box");
    const auto manager = rd_ptr(cint, "client.gui_manager");
    if (!panel || *panel == 0 || !manager || *manager == 0)
        return Result::fail("advance_tutorial: no live panel or manager");

    const auto before = call<int>("gui.panel_exists", reinterpret_cast<void*>(*manager),
                                  reinterpret_cast<void*>(*panel));
    if (!before || *before == 0)
        return Result::fail("advance_tutorial: tutorial panel is not listed");

    // 0x1f6 is the panel's native continue event. HandleInputEvent either
    // advances the tutorial or closes it through PopModalPanel. The close path
    // runs MessageBoxUnpause and OnPanelRemoved, restoring pause and input.
    const auto handled = call<int>("gui.tutorial_handle_input", reinterpret_cast<void*>(*panel),
                                   0x1f6, 1);
    const auto after = call<int>("gui.panel_exists", reinterpret_cast<void*>(*manager),
                                 reinterpret_cast<void*>(*panel));
    log("tutorial: HandleInputEvent(panel=%08x, event=0x1f6, active=1) rc=%d, listed=%d",
        static_cast<unsigned>(*panel), handled.value_or(-1), after.value_or(-1));
    if (!handled) return Result::fail("advance_tutorial: handler was not callable");
    return Result::success();
}

Result GameAdapter::finish_hidden_tutorial() {
    const Result req = require({"client.gui_manager", "gui.panel_exists", "gui.tutorial_box",
                                "gui.messagebox_callback", "gui.messagebox_callback_context",
                                "gui.messagebox_callback_arg", "gui.tutorial_unpause"});
    if (!req.ok) return req;
    const std::uintptr_t gui = gui_in_game();
    const auto manager = rd_ptr(client_internal(), "client.gui_manager");
    const auto panel = rd_ptr(gui, "gui.tutorial_box");
    if (gui == 0 || !manager || *manager == 0 || !panel || *panel == 0)
        return Result::fail("finish_hidden_tutorial: no live tutorial object or manager");
    const auto listed = call<int>("gui.panel_exists", reinterpret_cast<void*>(*manager),
                                  reinterpret_cast<void*>(*panel));
    const auto callback = rd_ptr(*panel, "gui.messagebox_callback");
    const auto context = rd_ptr(*panel, "gui.messagebox_callback_context");
    const auto arg = rd_ptr(*panel, "gui.messagebox_callback_arg");
    const Bound* expected = find("gui.tutorial_unpause");
    if (!listed || *listed != 0 || !callback || expected == nullptr || *callback != expected->addr ||
        !context || *context != *panel || !arg || *arg != 0)
        return Result::fail("finish_hidden_tutorial: skipped completion callback is not armed exactly");
    if (!callv("gui.tutorial_unpause", reinterpret_cast<void*>(*context), reinterpret_cast<void*>(*arg)))
        return Result::fail("finish_hidden_tutorial: completion callback was not callable");
    log("tutorial: invoked skipped MessageBoxUnpause(panel=%08x)", static_cast<unsigned>(*panel));
    return Result::success();
}

Result GameAdapter::dismiss_status_summary() {
    const Result req = require({"client.gui_manager", "gui.panel_exists", "gui.status_summary_panel",
                                "gui.status_summary_handle_input"});
    if (!req.ok) return req;
    const auto manager = rd_ptr(client_internal(), "client.gui_manager");
    if (!manager || *manager == 0) return Result::fail("dismiss_status_summary: no GUI manager");
    const auto panel = rd_ptr(gui_in_game(), "gui.status_summary_panel");
    if (!panel || *panel == 0)
        return Result::fail("dismiss_status_summary: no status-summary panel");
    const auto listed = call<int>("gui.panel_exists", reinterpret_cast<void*>(*manager),
                                  reinterpret_cast<void*>(*panel));
    if (!listed || *listed == 0)
        return Result::fail("dismiss_status_summary: status-summary panel is not listed");
    const std::uintptr_t vt = read_ptr(*panel).value_or(0);
    const auto slot = at_offset(vt, 0x3c);
    const std::uintptr_t handler = slot ? read_ptr(*slot).value_or(0) : 0;
    const Bound* expected = find("gui.status_summary_handle_input");
    if (expected == nullptr || handler != expected->addr)
        return Result::fail("dismiss_status_summary: listed panel is not CSWGuiStatusSummary");
    // The status-summary handler is void __thiscall.  Its return register is
    // not a success indicator; interpreting it as one could report failure
    // after the native teardown has already begun.
    if (!callv("gui.status_summary_handle_input", reinterpret_cast<void*>(*panel), 0x27, 1))
        return Result::fail("dismiss_status_summary: handler was not callable");
    log("status summary: HandleInputEvent(panel=%08x, event=0x27, active=1) rc=%d",
        static_cast<unsigned>(*panel), 1);
    return Result::success();
}

Result GameAdapter::equipment_screen(bool visible) {
    const char* site = visible ? "gui.show_sw_in_game_gui" : "gui.hide_sw_in_game_gui";
    const Result req = require({site, "gui.in_game_screen_active", "gui.last_gui_panel"});
    if (!req.ok) return req;
    const std::uintptr_t gui = gui_in_game();
    if (gui == 0) return Result::fail("equipment_screen: CGuiInGame is unavailable");
    const auto active = rd(gui, "gui.in_game_screen_active");
    const auto panel = rd(gui, "gui.last_gui_panel");
    if (!active || !panel) return Result::fail("equipment_screen: active screen state is unreadable");

    // Show/Hide are transitions, not idempotent setters: both run authored
    // callbacks and pause effects. Never replay either transition merely
    // because a client retried after a timeout.
    if (visible && *active != 0) {
        if (*panel == 0) return Result::success();
        return Result::fail("equipment_screen: another in-game screen is active");
    }
    if (!visible && *active == 0) return Result::success();
    if (!visible && *panel != 0)
        return Result::fail("equipment_screen: active screen is not equipment");

    // Hide takes a restore flag, not a panel selector. Restore=0 is the
    // native equipment-close path after the guarded panel check above.
    const auto state = call<int>(site, reinterpret_cast<void*>(gui), 0);
    if (!state || *state == 0)
        return Result::fail("equipment_screen: native GUI transition was rejected");
    const auto after_active = rd(gui, "gui.in_game_screen_active");
    const auto after_panel = rd(gui, "gui.last_gui_panel");
    if (!after_active || !after_panel || ((*after_active != 0) != visible) ||
        (visible && *after_panel != 0))
        return Result::fail("equipment_screen: native GUI transition did not reach the requested state");
    log("equipment screen: %s(panel=0) state=%d", visible ? "show" : "hide", *state);
    return Result::success();
}

Result GameAdapter::door_use(std::uint32_t door_id) {
    if (door_id == 0 || door_id == 0x7f000000u || door_id == 0xffffffffu)
        return Result::fail("door_use: invalid door object id");
    const Result req = require({"client.message_handler", "msg.change_door_state",
                                "server.get_game_object", "object.id", "object.type"});
    if (!req.ok) return req;
    const std::uintptr_t server = server_app();
    const auto handler = rd_ptr(client_internal(), "client.message_handler");
    if (server == 0 || !handler || *handler == 0)
        return Result::fail("door_use: no live server or client message handler");
    const auto object = call<std::uintptr_t>("server.get_game_object", reinterpret_cast<void*>(server), door_id);
    const auto id = object && *object ? rd(*object, "object.id") : std::nullopt;
    const auto type = object && *object ? rd(*object, "object.type") : std::nullopt;
    // CGameObject's internal byte uses 10 for doors, unlike NWScript's mask 8.
    if (!id || static_cast<std::uint32_t>(*id) != door_id || !type || *type != 10)
        return Result::fail("door_use: object id does not resolve to a live door");
    if (!callv("msg.change_door_state", reinterpret_cast<void*>(*handler), door_id, 0x2725))
        return Result::fail("door_use: retail message sender was not callable");
    log("door_use: dispatched ChangeDoorState(door=%08x, state=0x2725)", door_id);
    return Result::success();
}

// Door opening is two-phase on K1. CSWSDoor::OpenDoor -> SetOpenState writes
// only also_open_state (+0x2cd) and the animation id (+0xd4 = 0x2742). The
// committed open_state (+0x2cc, what GetIsOpen and the walkmesh read) is
// written only by CSWSDoor::MoveToNextOpenState, whose sole retail caller is
// the client's model-animation-done callback CSWCDoor::MoveNextDoorState --
// which the headless client never delivers for some doors. A door stuck there
// (+0xd4 != 0x2726 closed, +0x2cd = 1, +0x2cc = 0) makes every later
// creature-path open a no-op at AIActionOpenDoor (cmp [door+0xd4], 0x2726)
// and blocks the PC. This runs phase two once, on the CSWSDoor `this`.
Result GameAdapter::door_commit_open(std::uint32_t door_id) {
    if (door_id == 0 || door_id == 0x7f000000u || door_id == 0xffffffffu)
        return Result::fail("door_commit_open: invalid door object id");
    const Result req = require({"door.move_to_next_open_state", "server.get_game_object",
                                "object.id", "object.type"});
    if (!req.ok) return req;
    const std::uintptr_t server = server_app();
    if (server == 0) return Result::fail("door_commit_open: no live server");
    const auto object = call<std::uintptr_t>("server.get_game_object", reinterpret_cast<void*>(server), door_id);
    const auto id = object && *object ? rd(*object, "object.id") : std::nullopt;
    const auto type = object && *object ? rd(*object, "object.type") : std::nullopt;
    // CGameObject's internal byte uses 10 for doors, unlike NWScript's mask 8.
    if (!id || static_cast<std::uint32_t>(*id) != door_id || !type || *type != 10)
        return Result::fail("door_commit_open: object id does not resolve to a live door");
    // MoveToNextOpenState is a CSWSDoor method: reach the CSWSObject `this`
    // the same way server_dialog does rather than assuming the CGameObject
    // sits at offset 0 of the door.
    std::string why;
    const std::uintptr_t door = as_sws_object(*object, &why);
    if (door == 0) return Result::fail("door_commit_open: " + why);
    const int before = rd(door, "door.open_state").value_or(-1);
    if (!callv("door.move_to_next_open_state", reinterpret_cast<void*>(door)))
        return Result::fail("door_commit_open: door.move_to_next_open_state was not callable");
    const int after = rd(door, "door.open_state").value_or(-1);
    log("door_commit_open: MoveToNextOpenState(door=%08x this=0x%08X) open_state %d -> %d",
        door_id, static_cast<unsigned>(door), before, after);
    return Result::success();
}

Result GameAdapter::door_security(std::uint32_t door_id) {
    if (door_security_.armed || door_security_.ready)
        return Result::fail("door_security: one transaction is already pending");
    if (door_id == 0 || door_id == 0x7f000000u || door_id == 0xffffffffu)
        return Result::fail("door_security: invalid door object id");
    const Result req = require({"client.message_handler", "msg.unlock_object",
                                "server.get_game_object", "object.id", "object.type",
                                "door.locked", "door.lockable", "door.open_state",
                                "client.get_sw_party", "party.get_player_character",
                                "client_party.member", "client_party.member_id"});
    if (!req.ok) return req;
    const std::uintptr_t server = server_app();
    const auto handler = rd_ptr(client_internal(), "client.message_handler");
    const auto object = server ? call<std::uintptr_t>("server.get_game_object",
        reinterpret_cast<void*>(server), door_id) : std::nullopt;
    const auto id = object && *object ? rd(*object, "object.id") : std::nullopt;
    const auto type = object && *object ? rd(*object, "object.type") : std::nullopt;
    const auto locked = object && *object ? rd(*object, "door.locked") : std::nullopt;
    const auto lockable = object && *object ? rd(*object, "door.lockable") : std::nullopt;
    const auto open_state = object && *object ? rd(*object, "door.open_state") : std::nullopt;
    if (!handler || *handler == 0 || !object || *object == 0 || !id || !type || !locked || !lockable || !open_state)
        return Result::fail("door_security: live door or client message handler is unavailable");
    // CGameObject's internal byte uses 10 for doors, unlike NWScript's type mask 8.
    if (static_cast<std::uint32_t>(*id) != door_id || *type != 10)
        return Result::fail("door_security: object id does not resolve to a live door");
    if (*locked == 0 || *lockable == 0)
        return Result::fail("door_security: door is not a lockable locked target");

    const std::uintptr_t capp = client_app();
    const auto party = call<std::uintptr_t>("client.get_sw_party", reinterpret_cast<void*>(capp));
    const auto actor = party && *party ? call<std::uintptr_t>("party.get_player_character",
        reinterpret_cast<void*>(*party)) : std::nullopt;
    const auto slot0 = party && *party ? at_offset(*party, off("client_party.member", -1) +
        off("client_party.member_id", -1)) : std::nullopt;
    const auto actor_id = slot0 ? read_uint(*slot0, 4) : std::nullopt;
    const auto actual_id = actor && *actor ? rd(*actor, "object.id") : std::nullopt;
    if (!party || *party == 0 || !actor || *actor == 0 || !actor_id || !actual_id ||
        static_cast<std::uint32_t>(*actual_id) != static_cast<std::uint32_t>(*actor_id))
        return Result::fail("door_security: current party leader is unavailable or changed");

    door_security_ = PendingDoorSecurity{};
    door_security_.armed = true;
    door_security_.frames = 2;
    door_security_.party = *party;
    door_security_.actor = *actor;
    door_security_.door = *object;
    door_security_.actor_id = static_cast<std::uint32_t>(*actor_id);
    door_security_.result.door_id = door_id;
    door_security_.result.locked_before = *locked != 0;
    door_security_.result.open_state_before = static_cast<std::uint32_t>(*open_state);
    return Result::success();
}

void GameAdapter::step_door_security() {
    if (!door_security_.armed || --door_security_.frames > 0) return;
    auto finish = [this](Result status) {
        door_security_.status = std::move(status);
        door_security_.armed = false;
        door_security_.ready = true;
    };
    const std::uintptr_t server = server_app();
    const auto party = call<std::uintptr_t>("client.get_sw_party", reinterpret_cast<void*>(client_app()));
    const auto actor = party && *party ? call<std::uintptr_t>("party.get_player_character",
        reinterpret_cast<void*>(*party)) : std::nullopt;
    const auto slot0 = party && *party ? at_offset(*party, off("client_party.member", -1) +
        off("client_party.member_id", -1)) : std::nullopt;
    const auto actor_id = slot0 ? read_uint(*slot0, 4) : std::nullopt;
    const auto object = server ? call<std::uintptr_t>("server.get_game_object", reinterpret_cast<void*>(server),
        door_security_.result.door_id) : std::nullopt;
    const auto id = object && *object ? rd(*object, "object.id") : std::nullopt;
    const auto type = object && *object ? rd(*object, "object.type") : std::nullopt;
    const auto handler = rd_ptr(client_internal(), "client.message_handler");
    if (!party || *party != door_security_.party || !actor || *actor != door_security_.actor ||
        !actor_id || static_cast<std::uint32_t>(*actor_id) != door_security_.actor_id ||
        !object || *object != door_security_.door || !id || static_cast<std::uint32_t>(*id) != door_security_.result.door_id ||
        !type || *type != 10 || !handler || *handler == 0) {
        finish(Result::fail("door_security: actor or door changed before execution"));
        return;
    }
    if (!door_security_.dispatched) {
        // This is exactly CSWCDoor::MenuActionSecurity: invalid item id makes the
        // server evaluate Security rather than treating a caller-supplied item as a key.
        if (!callv("msg.unlock_object", reinterpret_cast<void*>(*handler), door_security_.result.door_id, 0x7f000000u)) {
            finish(Result::fail("door_security: retail Security sender was not callable"));
            return;
        }
        door_security_.dispatched = true;
        // The retail action may include a timing bar. Wait three seconds at the
        // normal client cadence before returning its engine-state postcondition.
        door_security_.frames = 180;
        return;
    }
    const auto locked = rd(*object, "door.locked");
    const auto open_state = rd(*object, "door.open_state");
    if (!locked || !open_state) { finish(Result::fail("door_security: post-dispatch door state is unreadable")); return; }
    door_security_.result.locked_after = *locked != 0;
    door_security_.result.open_state_after = static_cast<std::uint32_t>(*open_state);
    finish(Result::success());
}

bool GameAdapter::take_door_security_result(Result* status, DoorSecurityResult* out) {
    if (!door_security_.ready) return false;
    *status = std::move(door_security_.status);
    *out = door_security_.result;
    door_security_ = PendingDoorSecurity{};
    return true;
}

Result GameAdapter::attack(std::uint32_t target_id) {
    if (target_id == 0 || target_id == 0x7f000000u || target_id == 0xffffffffu)
        return Result::fail("attack: invalid target object id");
    const Result req = require({"client.message_handler", "msg.attack", "client.player_creature_id",
                                "server.client_to_server_object_id", "server.get_player_creature_id",
                                "server.get_game_object", "object.id", "object.type"});
    if (!req.ok) return req;
    const std::uintptr_t server = server_app();
    const auto handler = rd_ptr(client_internal(), "client.message_handler");
    const auto client_pc = rd(client_internal(), "client.player_creature_id");
    if (server == 0 || !handler || *handler == 0 || !client_pc)
        return Result::fail("attack: no live server, player or client message handler");
    const auto server_id = call<std::uint32_t>("server.client_to_server_object_id",
        reinterpret_cast<void*>(server), target_id);
    const auto pc = call<std::uint32_t>("server.get_player_creature_id", reinterpret_cast<void*>(server));
    if (!server_id || !pc || *pc == 0 || *pc == 0x7f000000u || *pc == 0xffffffffu)
        return Result::fail("attack: player or target identity is unavailable");
    if (target_id == static_cast<std::uint32_t>(*client_pc) || *server_id == *pc)
        return Result::fail("attack: refusing to attack the player itself");
    const auto object = call<std::uintptr_t>("server.get_game_object", reinterpret_cast<void*>(server), *server_id);
    const auto id = object && *object ? rd(*object, "object.id") : std::nullopt;
    const auto type = object && *object ? rd(*object, "object.type") : std::nullopt;
    if (!id || static_cast<std::uint32_t>(*id) != *server_id || !type || *type != 5)
        return Result::fail("attack: target does not resolve to a live creature");
    // Send the original client id; the server owns target conversion and combat.
    if (!callv("msg.attack", reinterpret_cast<void*>(*handler), target_id, std::uint16_t{0}))
        return Result::fail("attack: retail message sender was not callable");
    log("attack: dispatched Input_Attack(target=%08x, combatFeat=0)", target_id);
    return Result::success();
}

Result GameAdapter::dismiss_messagebox() {
    const Result req = require({"client.gui_manager", "gui.modal_data", "gui.modal_size",
                                "gui.messagebox_handle_input", "client.input_class"});
    if (!req.ok) return req;
    const auto manager = rd_ptr(client_internal(), "client.gui_manager");
    if (!manager || *manager == 0) return Result::fail("dismiss_messagebox: no GUI manager");
    const auto before = rd(*manager, "gui.modal_size");
    const auto data = rd_ptr(*manager, "gui.modal_data");
    if (!before || *before <= 0 || *before > 128 || !data || *data == 0)
        return Result::fail("dismiss_messagebox: invalid or empty modal stack");
    const auto top_at = at_offset(*data,
        static_cast<std::int64_t>(*before - 1) * sizeof(std::uintptr_t));
    const std::uintptr_t top = top_at ? read_ptr(*top_at).value_or(0) : 0;
    const std::uintptr_t vt = top != 0 ? read_ptr(top).value_or(0) : 0;
    const auto slot = vt != 0 ? at_offset(vt, 0x3c) : std::nullopt;
    const std::uintptr_t handler = slot ? read_ptr(*slot).value_or(0) : 0;
    const Bound* expected = find("gui.messagebox_handle_input");
    // This proves the native handler identity, including subclasses inheriting
    // it. It does not identify a unique concrete class or the message text.
    if (top == 0 || expected == nullptr || handler != expected->addr)
        return Result::fail("dismiss_messagebox: top modal does not use CSWGuiMessageBox input");
    const int input_before = rd(client_internal(), "client.input_class").value_or(-1);
    // Native OK owns PopModalPanel, lifecycle cleanup and the armed callback.
    // Never remove/pop the panel or invoke its callback again after dispatch.
    if (!callv("gui.messagebox_handle_input", reinterpret_cast<void*>(top), 0x1f6, 1))
        return Result::fail("dismiss_messagebox: handler was not callable");
    const auto after = rd(*manager, "gui.modal_size");
    if (!after || *after != *before - 1)
        return Result::fail("dismiss_messagebox: native OK did not decrement the modal stack");
    if (*after > 0) {
        const auto remaining = rd_ptr(*manager, "gui.modal_data");
        const auto next_at = remaining && *remaining != 0
            ? at_offset(*remaining, static_cast<std::int64_t>(*after - 1) * sizeof(std::uintptr_t))
            : std::nullopt;
        const auto next = next_at ? read_ptr(*next_at) : std::nullopt;
        if (!next || *next == 0 || *next == top)
            return Result::fail("dismiss_messagebox: native OK did not replace the top modal");
    }
    const int input_after = rd(client_internal(), "client.input_class").value_or(-1);
    log("messagebox: native OK(panel=%08x), modal %d -> %d, input %d -> %d",
        static_cast<unsigned>(top), *before, *after, input_before, input_after);
    return Result::success();
}

Result GameAdapter::container_input(const char* action, int event, bool require_take_all) {
    const Result req = require({"client.gui_manager", "gui.modal_data", "gui.modal_size",
                                "gui.panel_exists", "gui.container_handle_input"});
    if (!req.ok) return req;
    const auto manager = rd_ptr(client_internal(), "client.gui_manager");
    if (!manager || *manager == 0) return Result::fail(std::string(action) + ": no GUI manager");
    const auto before = rd(*manager, "gui.modal_size");
    const auto data = rd_ptr(*manager, "gui.modal_data");
    if (!before || *before <= 0 || !data || *data == 0)
        return Result::fail(std::string(action) + ": modal stack is empty");
    const auto top_at = at_offset(*data,
        static_cast<std::int64_t>(*before - 1) * sizeof(std::uintptr_t));
    const std::uintptr_t top = top_at ? read_ptr(*top_at).value_or(0) : 0;
    const std::uintptr_t vt = top != 0 ? read_ptr(top).value_or(0) : 0;
    const auto slot = at_offset(vt, 0x3c);
    const std::uintptr_t handler = slot ? read_ptr(*slot).value_or(0) : 0;
    const Bound* expected = find("gui.container_handle_input");
    if (top == 0 || expected == nullptr || handler != expected->addr)
        return Result::fail(std::string(action) + ": top modal is not CSWGuiContainer");
    const auto exists = call<int>("gui.panel_exists", reinterpret_cast<void*>(*manager),
                                  reinterpret_cast<void*>(top));
    if (!exists || *exists == 0)
        return Result::fail(std::string(action) + ": top container panel is not listed");

    if (require_take_all) {
        const int selector_off = off("gui.container_take_all", lay_.container_take_all);
        const int mode_off = off("gui.container_mode", lay_.container_mode);
        if (selector_off < 0) return Result::unsupported("gui.container_take_all");
        if (mode_off < 0) return Result::unsupported("gui.container_mode");
        const auto selector_at = at_offset(top, selector_off);
        const auto mode_at = at_offset(top, mode_off);
        // HandleInputEvent compares the byte SetContainer stored at +0x68.
        // Reading the surrounding dword would reject a valid selector when
        // adjacent bytes contain unrelated state.
        const auto selector = selector_at ? read_uint(*selector_at, 1) : std::nullopt;
        const auto mode = mode_at
            ? read_uint(*mode_at, width("gui.container_mode")) : std::nullopt;
        if (!selector || *selector != 1)
            return Result::fail(std::string(action) + ": container does not permit native Take All");
        if (!mode || (*mode & 1u) == 0)
            return Result::fail(std::string(action) + ": container is not in normal inventory mode");
    }

    if (!callv("gui.container_handle_input", reinterpret_cast<void*>(top), event, 1))
        return Result::fail(std::string(action) + ": handler was not callable");

    const auto after = rd(*manager, "gui.modal_size");
    const auto still_exists = call<int>("gui.panel_exists", reinterpret_cast<void*>(*manager),
                                        reinterpret_cast<void*>(top));
    if (!after || *after != *before - 1 || !still_exists || *still_exists != 0)
        return Result::fail(std::string(action) + ": native event did not retire the panel");
    log("container: %s HandleInputEvent(panel=%08x, event=0x%x, active=1), modal %d -> %d",
        action, static_cast<unsigned>(top), event, *before, *after);
    return Result::success();
}

Result GameAdapter::dismiss_container() {
    // CGuiInGame::RemoveGUIPopUps uses exactly event 0x28. This path sends
    // GUI_CONTAINER/Close(take_all=0), calls HideContainerGui, pops and
    // removes the panel, restores input class, and clears the panel pause.
    return container_input("dismiss_container", 0x28, false);
}

Result GameAdapter::take_all_container() {
    // In normal container mode, event 0x27 sends GUI_CONTAINER/Close with the
    // selector stored by SetContainer at +0x68. Requiring selector==1 keeps
    // this command from degrading into an ordinary close on another mode.
    return container_input("take_all_container", 0x27, true);
}

Result GameAdapter::accept_party_selection() {
    const Result req = require({"client.gui_manager", "client.get_in_game_gui",
                                "gui.modal_data", "gui.modal_size", "gui.panel_exists",
                                "gui.party_selection_accept_party", "gui.party_selection_vtable",
                                "gui.initialized", "gui.party_selection_selected_count",
                                "gui.party_selection_mode", "gui.party_selection_entry0_flags",
                                "client.input_class", "server.pause_state"});
    if (!req.ok) return req;
    const std::uintptr_t gui = gui_in_game();
    if (gui == 0 || rd(gui, "gui.initialized").value_or(0) == 0)
        return Result::fail("accept_party_selection: in-game GUI is not initialized");
    const auto manager = rd_ptr(client_internal(), "client.gui_manager");
    if (!manager || *manager == 0)
        return Result::fail("accept_party_selection: no GUI manager");
    const auto before = rd(*manager, "gui.modal_size");
    const auto data = rd_ptr(*manager, "gui.modal_data");
    if (!before || *before <= 0 || !data || *data == 0)
        return Result::fail("accept_party_selection: modal stack is empty");
    const auto top_at = at_offset(*data,
        static_cast<std::int64_t>(*before - 1) * sizeof(std::uintptr_t));
    const std::uintptr_t top = top_at ? read_ptr(*top_at).value_or(0) : 0;
    const Bound* expected_vtable = find("gui.party_selection_vtable");
    const std::uintptr_t vtable = top != 0 ? read_ptr(top).value_or(0) : 0;
    if (top == 0 || expected_vtable == nullptr || vtable != expected_vtable->addr)
        return Result::fail("accept_party_selection: top modal is not CSWGuiPartySelection");
    if (!panel_is_listed(*manager, top))
        return Result::fail("accept_party_selection: top party-selection panel is not listed");

    const auto selected = rd(top, "gui.party_selection_selected_count");
    const auto mode = rd(top, "gui.party_selection_mode");
    const auto entry0 = rd(top, "gui.party_selection_entry0_flags");
    if (!selected || *selected != 1 || !mode || *mode != 1 || !entry0 || (*entry0 & 0x4) == 0)
        return Result::fail("accept_party_selection: selection is not the validated initialized state");

    if (!callv("gui.party_selection_accept_party", reinterpret_cast<void*>(top)))
        return Result::fail("accept_party_selection: AcceptParty was not callable");

    const auto after = rd(*manager, "gui.modal_size");
    const auto after_data = rd_ptr(*manager, "gui.modal_data");
    bool still_modal = false;
    if (after && after_data && *after_data != 0 && *after >= 0 && *after <= 128) {
        for (int i = 0; i < *after; ++i) {
            const auto slot = at_offset(*after_data,
                static_cast<std::int64_t>(i) * sizeof(std::uintptr_t));
            if (slot && read_ptr(*slot).value_or(0) == top) still_modal = true;
        }
    }
    const int input_class = rd(client_internal(), "client.input_class").value_or(-1);
    const int pause = rd(server_internal(), "server.pause_state").value_or(-1);
    const int accepted_mode = rd(top, "gui.party_selection_mode").value_or(-1);
    const int accepted_flags = rd(top, "gui.party_selection_entry0_flags").value_or(-1);
    if (!after || !after_data || still_modal || accepted_mode != 0 || (accepted_flags & 0x4) != 0)
        return Result::fail("accept_party_selection: native acceptance did not retire the modal");
    log("party selection: AcceptParty(panel=%08x), modal %d -> %d, input=%d, pause=%d",
        static_cast<unsigned>(top), *before, *after, input_class, pause);
    return Result::success();
}

Result GameAdapter::set_fixed_step(int hz) {
    if (hz < 0 || hz > 100000) return Result::fail("fixed_step: hz must be 0 (off) or 1..100000");
    if (!fixed_step_fits(hz, g_harness_scale.load(std::memory_order_acquire)))
        return Result::fail("fixed_step: scale * 1e6 / hz overflows the fixed-step increment");
    const Result req = require({"g.app_manager", "client.get_world_timer", "client.get_pause_timer",
                                "client.get_animation_timer", "timer.set_fixed_snapshot_rate",
                                "timer.pause_world_timer", "timer.unpause_world_timer"});
    if (!req.ok) return req;
    const std::uintptr_t capp = client_app();
    if (capp == 0) return Result::fail("fixed_step: no client");

    // The five timers SetGameSpeed scales (clientexoappinternal.cpp:2808-2835):
    // client world / pause / animation (clientexoapp.cpp:116,131,146), server
    // world / pause (serverexoapp.cpp:333,363). SetFixedSnapshotRate(this, on,
    // hz) zeroes snapshot_time_1/2 (worldtimer.cpp:277-280), which rewinds
    // GetWorldTime unless the timer is paused around it (RE audit 3). A timer
    // the engine already paused is left paused.
    std::vector<std::uintptr_t> timers;
    for (const char* site : {"client.get_world_timer", "client.get_pause_timer", "client.get_animation_timer"})
        if (const auto t = call<std::uintptr_t>(site, reinterpret_cast<void*>(capp)); t && *t != 0)
            timers.push_back(*t);
    if (const std::uintptr_t sapp = server_app(); sapp != 0) {
        const std::uintptr_t sint = server_internal();
        if (const std::uintptr_t t = via_call_or_field("server.get_world_timer", sapp, "server.world_timer", sint, false); t != 0)
            timers.push_back(t);
        if (const std::uintptr_t t = via_call_or_field("server.get_pause_timer", sapp, "server.pause_timer", sint, false); t != 0)
            timers.push_back(t);
    }
    const int paused_off = off("timer.paused", lay_.timer_paused);
    if (paused_off < 0) return Result::unsupported("timer.paused");
    for (const std::uintptr_t t : timers) {
        const auto paused_at = at_offset(t, paused_off);
        if (!paused_at) continue;
        const bool was_paused = read_int(*paused_at, 4).value_or(0) != 0;
        if (!was_paused) callv("timer.pause_world_timer", reinterpret_cast<void*>(t));
        callv("timer.set_fixed_snapshot_rate", reinterpret_cast<void*>(t), hz > 0 ? 1 : 0, hz);
        if (!was_paused) callv("timer.unpause_world_timer", reinterpret_cast<void*>(t));
    }
    fixed_hz_ = hz;
    log("fixed_step: hz=%d on %zu timer(s)", hz, timers.size());
    return Result::success();
}

Result GameAdapter::set_movies(bool enabled) {
    if (!have("client.play_movies")) return Result::unsupported("client.play_movies");
    g_movies_enabled.store(enabled, std::memory_order_release);
    return Result::success();
}

bool GameAdapter::movies_enabled() { return g_movies_enabled.load(std::memory_order_acquire); }

// ------------------------------------------------------- globals, journal --

Result GameAdapter::walk_globals(GlobalsVisitor& v) {
    const Result req = require({"g.app_manager", "gvt.identifiers", "gvt.bools", "gvt.numbers", "gvt.strings"});
    if (!req.ok) return req;
    if (!have("app.get_global_variable_table") && !have("gvt.table"))
        return Result::unsupported("app.get_global_variable_table");
    const std::uintptr_t sapp = server_app();
    if (sapp == 0) return Result::fail("globals: no server");
    // CSWGlobalVariableTable* CServerExoApp::GetGlobalVariableTable(this):
    // serverexoapp.cpp:413; or the table embedded in the server internal.
    const std::uintptr_t gvt = via_call_or_field("app.get_global_variable_table", sapp, "gvt.table",
                                                 server_internal(), true);
    if (gvt == 0) return Result::fail("globals: no table");

    const int istride = stride("gvt.identifier", lay_.gvt_identifier_stride);
    const int name_len = off("gvt.identifier_type_index", lay_.gvt_name_len);
    int slots = lay_.gvt_slot_count;
    if (const Bound* ids_site = find("gvt.identifiers"); ids_site != nullptr && istride > 0 && ids_site->size > 0)
        slots = static_cast<int>(ids_site->size / static_cast<std::uint32_t>(istride));
    if (slots <= 0 || istride <= 0 || name_len <= 0) return Result::unsupported("gvt.identifier");

    const auto ids_at = at_offset(gvt, off("gvt.identifiers", 0));
    const auto bools_at = at_offset(gvt, off("gvt.bools", 0));
    const auto numbers_at = at_offset(gvt, off("gvt.numbers", 0));
    const auto strings_at = at_offset(gvt, off("gvt.strings", 0));
    if (!ids_at || !bools_at || !numbers_at || !strings_at)
        return Result::fail("globals: a typed array offset does not fit the table pointer");
    const std::uintptr_t ids = *ids_at;
    const std::uintptr_t bools = *bools_at;
    const std::uintptr_t numbers = *numbers_at;
    const std::uintptr_t strings = *strings_at;

    // Counts bound each typed array (globalvartables.cpp:318-362); without a
    // count the walk still probes every read, so a bad index yields a skipped
    // entry rather than a fault.
    auto count_at = [&](const char* site, int def) {
        const auto at = at_offset(gvt, off(site, def));
        return at ? read_int(*at, 4).value_or(-1) : -1;
    };
    const int n_bool = count_at("gvt.boolean_count", lay_.gvt_bool_count);
    const int n_num  = count_at("gvt.number_count", lay_.gvt_number_count);
    const int n_str  = count_at("gvt.string_count", lay_.gvt_string_count);

    if (!readable(ids, static_cast<std::size_t>(slots) * static_cast<std::size_t>(istride)))
        return Result::fail("globals: identifiers unreadable");
    char name[64];
    for (int i = 0; i < slots; ++i) {
        const auto id_at = at_index(ids, i, istride);
        if (!id_at) break;
        const std::uintptr_t id = *id_at;
        const char* raw = reinterpret_cast<const char*>(id);
        if (raw[0] == '\0') continue;   // empty slot in the open-addressed table
        const int n = name_len < 63 ? name_len : 63;
        std::memcpy(name, raw, static_cast<std::size_t>(n));
        name[n] = '\0';
        const auto tai_at = at_offset(id, name_len);
        if (!tai_at) continue;
        const auto tai = read_uint(*tai_at, 2);
        if (!tai) continue;
        const GlobalKind k = decode_global_kind(static_cast<std::uint16_t>(*tai));
        switch (k.type) {
        case 0: {
            if (n_bool >= 0 && static_cast<int>(k.index) >= n_bool) break;
            const auto byte_at = at_offset(bools, k.index >> 3);
            const auto byte = byte_at ? read_uint(*byte_at, 1) : std::nullopt;
            if (byte) { const std::uint8_t b = static_cast<std::uint8_t>(*byte); v.on_bool(name, gvt_bool(&b, k.index & 7)); }
            break;
        }
        case 1: {
            if (n_num >= 0 && static_cast<int>(k.index) >= n_num) break;
            // SetGlobalNumber stores one signed byte (-128..127 per nwscript.nss).
            const auto num_at = at_offset(numbers, k.index);
            if (const auto val = num_at ? read_int(*num_at, 1) : std::nullopt; val)
                v.on_number(name, *val);
            break;
        }
        case 3: {
            if (n_str >= 0 && static_cast<int>(k.index) >= n_str) break;
            const auto str_at = at_index(strings, k.index, sizeof(CExoString));
            if (const auto s = str_at ? read_exostring_at(*str_at) : std::nullopt; s)
                v.on_string(name, s->c_str());
            break;
        }
        default: break;   // locations: no visitor slot
        }
    }
    return Result::success();
}

Result GameAdapter::walk_journal(JournalVisitor& v) {
    const Result req = require({"g.app_manager", "journal.entries"});
    if (!req.ok) return req;
    if (!have("app.get_party_table") && !have("party.table")) return Result::unsupported("app.get_party_table");
    const int estride = stride("journal.entry", lay_.journal_entry_stride);
    const int tag_off = off("journal.entry_tag", lay_.journal_tag);
    const int state_off = off("journal.entry_state", lay_.journal_state);
    const int data_off = off("journal.data", lay_.journal_data);
    const int size_off = off("journal.size", lay_.journal_size);
    if (estride <= 0 || tag_off < 0) return Result::unsupported("journal.entry");
    if (state_off < 0) return Result::unsupported("journal.entry_state");
    if (data_off < 0 || size_off < 0) return Result::unsupported("journal.data");
    const std::uintptr_t sapp = server_app();
    if (sapp == 0) return Result::fail("journal: no server");
    // CSWPartyTable* CServerExoApp::GetPartyTable(this): serverexoapp.cpp:428;
    // or the table embedded in the server internal.
    const std::uintptr_t party = via_call_or_field("app.get_party_table", sapp, "party.table", server_internal(), true);
    if (party == 0) return Result::fail("journal: no party table");
    // CSWSJournal* at CSWPartyTable+journal.entries, nullable (RE audit 9):
    // {SJournalEntry* data, int size, int capacity}.
    const auto journal = rd_ptr(party, "journal.entries");
    if (!journal) return Result::fail("journal: journal.entries not readable");
    if (*journal == 0) return Result::success();
    const auto data_at = at_offset(*journal, data_off);
    const auto size_at = at_offset(*journal, size_off);
    if (!data_at || !size_at) return Result::fail("journal: header offsets do not fit the pointer");
    const std::uintptr_t data = read_ptr(*data_at).value_or(0);
    const int size = read_int(*size_at, 4).value_or(0);
    if (data == 0 || size <= 0) return Result::success();
    if (size > 4096) return Result::fail("journal: implausible size");
    for (int i = 0; i < size; ++i) {
        const auto e = at_index(data, i, estride);
        if (!e) break;
        const auto tag_at = at_offset(*e, tag_off);
        const auto state_at = at_offset(*e, state_off);
        if (!tag_at || !state_at) break;
        const auto tag = read_exostring_at(*tag_at);
        const auto state = read_int(*state_at, 4);
        if (tag && state) v.on_entry(tag->c_str(), *state);
    }
    return Result::success();
}

std::vector<std::string> GameAdapter::missing_sites() { return missing_; }

// ------------------------------------------------------------- K1 layout --

const Layout& k1_layout() {
    static const Layout l;   // the defaults in fields.hpp are the K1 values
    return l;
}

std::unique_ptr<EngineAdapter> make_k1_adapter(const hooks::AddressTable& table, std::uintptr_t image_base) {
    return std::make_unique<GameAdapter>("k1", k1_layout(), table, image_base);
}

std::unique_ptr<EngineAdapter> make_adapter(const hooks::AddressTable& table, std::uintptr_t image_base) {
    std::string game = table.game();
    for (char& c : game) c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    const bool k2 = game == "k2" || game == "kotor2" || game == "tsl" || table.build().rfind("k2_", 0) == 0;
    return k2 ? make_k2_adapter(table, image_base) : make_k1_adapter(table, image_base);
}

}  // namespace kp::harness

#endif  // i386
