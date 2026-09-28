// Field access, call shapes, layouts and the pure predicates the adapters share.
//
// Three kinds of number appear in an adapter, and they are kept apart:
//
//   * ADDRESSES of engine functions and globals: always from the address table,
//     by logical site name. Never in a .cpp file.
//   * OFFSETS the design lists as `field` sites (server.server_mode,
//     gui.reply_count, ...): also from the table. A missing one makes the
//     method that needs it unsupported.
//   * STRUCT LAYOUT the design does not list -- strides, vtable slots, the
//     `internal` pointer at +4 of the two app objects: a per-game Layout below,
//     each value cited to the corpus. Every Layout value can still be overridden
//     by a field site of the documented name, so a build that differs is a data
//     change, not a code change.
//
// FIELD SITES
// ===========
// SiteKind::Field and Site::offset / Site::size come from src/hooks/registry.hpp.
// A Field row is resolved iff its size is non-zero; addr is the owning global
// for a field anchored at one and 0 through a pointer chain.
#pragma once

#include <cctype>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <initializer_list>
#include <optional>
#include <string>
#include <string_view>
#include <unordered_map>
#include <vector>

#include "harness/engine.hpp"
#include "hooks/registry.hpp"
#include "hooks/thiscall.hpp"
#include "platform/platform.hpp"
#include "runtime/runtime.hpp"

namespace kp::harness {

// ------------------------------------------------------------ call shapes ---
//
// Amendment 6: KP_THISCALL is right on every i386 Windows build, but the
// native kotor2 ELF is GCC code and `this` is the first stack argument, cdecl.
// The registry never parses a convention; the adapter chooses from
// AddressTable::platform_name() and hardcodes the shape per call.

template <typename Ret, typename... Args>
using StackThisFn = Ret(__attribute__((cdecl)) *)(void*, Args...);

template <typename Ret, typename... Args>
using StdcallFn = Ret(__attribute__((stdcall)) *)(Args...);

template <typename Ret, typename... Args>
using CdeclFn = Ret(__attribute__((cdecl)) *)(Args...);

enum class CallShape { ThisInEcx, ThisOnStack };

inline CallShape call_shape_for_platform(std::string_view platform) {
    return platform == "linux" ? CallShape::ThisOnStack : CallShape::ThisInEcx;
}

template <typename Ret, typename... Args>
Ret call_this(CallShape shape, std::uintptr_t fn, void* self, Args... args) {
    if (shape == CallShape::ThisOnStack)
        return reinterpret_cast<StackThisFn<Ret, Args...>>(fn)(self, args...);
    return reinterpret_cast<hooks::ThiscallFn<Ret, Args...>>(fn)(self, args...);
}

// A site called with no `this` at all. One site needs it:
// CSWCMessage::SendPlayerToServerArea_AreaLoaded reaches the net layer through
// g_pAppManager and never reads ecx, and its body at 0x006778f0 ends in a bare
// `ret` -- no stack argument either, on either shape.
template <typename Ret, typename... Args>
Ret call_static(CallShape shape, std::uintptr_t fn, Args... args) {
    if (shape == CallShape::ThisOnStack)
        return reinterpret_cast<CdeclFn<Ret, Args...>>(fn)(args...);
    return reinterpret_cast<StdcallFn<Ret, Args...>>(fn)(args...);
}

// Every engine call runs inside an unarmed hook-body frame.
struct HookBodyScope {
    HookBodyScope() { runtime::enter_hook_body(); }
    ~HookBodyScope() { runtime::leave_hook_body(); }
    HookBodyScope(const HookBodyScope&) = delete;
    HookBodyScope& operator=(const HookBodyScope&) = delete;
};

// ------------------------------------------------------- field site reads --

inline bool site_is_field(const hooks::Site& s) { return s.kind == hooks::SiteKind::Field; }
inline std::uint32_t site_offset(const hooks::Site& s) { return s.offset; }
inline std::uint32_t site_size(const hooks::Site& s) { return s.size; }

// One table entry after binding, copied out so the adapter does not hold a
// reference into the runtime's table.
//
// Field rows follow data/hooksites.toml: `offset` and `size` describe the
// member; `addr` is the owning global for a field anchored at one
// (g.app_manager) and 0 through a pointer chain; a `sizeof` row has offset 0
// and carries the record stride in `size`. A field with size 0 is unresolved.
struct Bound {
    bool           ok = false;      // resolved and usable
    bool           is_field = false;
    std::uintptr_t addr = 0;        // runtime VA for functions, globals, anchored fields
    std::uint32_t  offset = 0;      // for fields
    std::uint32_t  size = 0;        // for fields: width, or stride for sizeof rows
};

// ----------------------------------------------------------- raw reads -----
//
// Every read probes platform::is_readable over the whole span first. A wrong
// pointer yields nullopt, never a fault.

inline bool readable(std::uintptr_t addr, std::size_t n) {
    return addr != 0 && platform::is_readable(reinterpret_cast<const void*>(addr), n);
}

// base + offset, refused when it would wrap. This is the one place the
// adapter does address arithmetic: on the 32-bit build a stale pointer plus a
// large offset wraps to a small address that is readable but unrelated, and
// the probe then answers about memory nobody asked for. Refusing here turns
// that into a nullopt the caller already handles. A negative offset is an
// unresolved site (-1), not an address.
inline std::optional<std::uintptr_t> at_offset(std::uintptr_t base, std::int64_t offset) {
    if (base == 0 || offset < 0) return std::nullopt;
    const std::uintptr_t o = static_cast<std::uintptr_t>(static_cast<std::uint64_t>(offset));
    if (static_cast<std::uint64_t>(offset) > static_cast<std::uint64_t>(~std::uintptr_t(0)) ||
        o > static_cast<std::uintptr_t>(~std::uintptr_t(0)) - base)
        return std::nullopt;
    return base + o;
}

// base + index * stride, every step checked the same way.
inline std::optional<std::uintptr_t> at_index(std::uintptr_t base, std::int64_t index,
                                              std::int64_t stride) {
    if (index < 0 || stride <= 0) return std::nullopt;
    const std::uint64_t span = static_cast<std::uint64_t>(index) * static_cast<std::uint64_t>(stride);
    if (span > static_cast<std::uint64_t>(~std::uintptr_t(0))) return std::nullopt;
    return at_offset(base, static_cast<std::int64_t>(span));
}

inline std::optional<std::uint32_t> read_uint(std::uintptr_t addr, unsigned size) {
    if (size == 0) size = 4;
    if (size != 1 && size != 2 && size != 4) return std::nullopt;
    if (!readable(addr, size)) return std::nullopt;
    std::uint32_t v = 0;
    std::memcpy(&v, reinterpret_cast<const void*>(addr), size);
    return v;
}

// A write for the rare case a real engine function is not the right
// instrument: forcing a single adjudicated struct field that an engine
// function itself reads every frame (e.g. CSWSDialog::Skippable, so
// IsDialogDelay honours a skip request on a DLG the author did not mark
// skippable). Same safety shape as the Lua kp.mem.* write funnel --
// readability probed first, protection restored after, every write logged --
// without a lua_State, since native harness commands run outside Lua.
inline bool write_uint(std::uintptr_t addr, std::uint32_t value, unsigned size,
                       const char* why) {
    if (size == 0) size = 4;
    if (size != 1 && size != 2 && size != 4) return false;
    if (!readable(addr, size)) return false;
    void* dst = reinterpret_cast<void*>(addr);
    if (!platform::set_protection(dst, size, platform::Protect::ReadWrite)) return false;
    std::memcpy(dst, &value, size);
    platform::set_protection(dst, size, platform::Protect::ReadWrite);
    platform::log(platform::LogLevel::Info, "harness write 0x%08X %u bytes = %u  <- %s",
                  static_cast<unsigned>(addr), size, value, why ? why : "(unknown site)");
    return true;
}

inline std::optional<std::int32_t> read_int(std::uintptr_t addr, unsigned size) {
    const auto u = read_uint(addr, size);
    if (!u) return std::nullopt;
    if (size == 0) size = 4;
    if (size == 1) return static_cast<std::int8_t>(*u);
    if (size == 2) return static_cast<std::int16_t>(*u);
    return static_cast<std::int32_t>(*u);
}

inline std::optional<std::uintptr_t> read_ptr(std::uintptr_t addr) {
    const auto v = read_uint(addr, sizeof(std::uintptr_t));
    if (!v) return std::nullopt;
    return static_cast<std::uintptr_t>(*v);
}

// The engine's string: {char* c_string; ulong length}, always by pointer.
// K1 include/types.h:2969-2973 (sizecheck 8). `length` counts the buffer, so
// for the engine's own strings it includes the trailing NUL (observed live on
// RunScript's name, see runtime/hook_bodies.cpp).
struct CExoString {
    char*         c_string;
    std::uint32_t length;
};
static_assert(sizeof(CExoString) == 8, "CExoString is two 32-bit fields");

constexpr std::uint32_t kMaxEngineString = 64 * 1024;

// Read a CExoString that lives at `addr`. Strips exactly one trailing NUL.
inline std::optional<std::string> read_exostring_at(std::uintptr_t addr) {
    if (!readable(addr, sizeof(CExoString))) return std::nullopt;
    CExoString s{};
    std::memcpy(&s, reinterpret_cast<const void*>(addr), sizeof s);
    if (s.c_string == nullptr || s.length == 0) return std::string();
    if (s.length > kMaxEngineString) return std::nullopt;
    if (!readable(reinterpret_cast<std::uintptr_t>(s.c_string), s.length)) return std::nullopt;
    std::uint32_t len = s.length;
    if (s.c_string[len - 1] == '\0') --len;
    return std::string(s.c_string, len);
}

// A CExoString the harness owns: the engine may read it and must never assign
// into it (amendment 8 of the RE audit). Not movable, because the view points
// into the buffer.
class OwnedExoString {
public:
    explicit OwnedExoString(std::string text) : text_(std::move(text)) {
        view_.c_string = text_.data();   // std::string keeps a NUL past size()
        view_.length   = static_cast<std::uint32_t>(text_.size() + 1);
    }
    OwnedExoString(const OwnedExoString&) = delete;
    OwnedExoString& operator=(const OwnedExoString&) = delete;
    CExoString* ptr() { return &view_; }

private:
    std::string text_;
    CExoString  view_{};
};

// ---------------------------------------------------------------- layout ---
//
// Values the design does not carry as field sites. -1 means unknown on this
// game; a method that needs it reports unsupported naming the override site.
// Each value can be overridden by a field site of the name in the comment.

struct Layout {
    // CAppManager {buffer, client@+4, server@+8, ..., reentrant_server_stats@+0x14}
    // K1 include/types.h:283-292. K2 mac main.cpp reads server at +8.
    int mgr_client = 4;                 // appmgr.client
    int mgr_server = 8;                 // appmgr.server
    int mgr_stats  = 0x14;              // appmgr.reentrant_server_stats
    // CClientExoApp / CServerExoApp = {vtable, internal}: K1 serverexoapp.cpp
    // `this->internal`; K2 ELF CClientExoApp::MainLoop wrapper `mov eax,[eax+4]`.
    int app_internal = 4;               // client.internal / server.internal

    // CSWGuiPanel vtable slot 27 (+0x6c) is SelectReply on the dialog panel:
    // K1 swguidialog.cpp:335 `(panel.vtable)->field27_0x6c(selection_index)`.
    int panel_select_reply_slot = 27;   // no site; dialog.select_reply is the call fallback
    // GameObjectMethods {destructor, SetId, ResetUpdateTimes, AsSWCObject,
    // AsSWSObject, ...}: K1 include/types.h:13186-13190 -> slot 4.
    int gameobject_as_sws_slot = 4;     // no site

    // CGuiInGame: the dialog panel pointer and the selection-pending flag.
    // K1 types.h:3074-3128 (+0x3c panel, +0xd0 pending); K2 gog guiingame.cpp
    // UpdateDialog reads panel +0x3c, pending +0xe8.
    int gui_dialog_panel = 0x3c;        // gui.dialog_panel
    int gui_selection_pending = 0xd0;   // gui.dialog_pending

    // CSWGuiContainer mode/action state. SetContainer stores its take-all
    // selector at +0x68 and sets bit 0 at +0x6c for the normal container
    // inventory mode. HandleInputEvent(0x27, 1) consumes both fields. These
    // K1 offsets and semantics were live-validated on the ordinary Endar
    // Spire locker; K2 leaves them unknown until it has its own binding.
    int container_take_all = 0x68;      // gui.container_take_all
    int container_mode = 0x6c;          // gui.container_mode

    // CSWGuiDialog: current server entry index and visible row count.
    // K1 guiingame.cpp:6227 (+0x64), _006a.cpp:463-480 (+0x6c);
    // K2 gog swguidialog.cpp:161-305 (+0x68, +0x70).
    int panel_entry = 0x64;             // dialog.panel_current_entry
    int panel_visible_count = 0x6c;     // dialog.panel_visible_count

    // CSWSDialog entries: stride and the per-entry link list.
    // K1 types.h:10377-10528, nwsdialog.cpp:1352-1365; K2 gog _0075.cpp HandleReply.
    int dialog_entry_stride = 0xb0;     // dialog.entry (sizeof row, stride in size)
    int dialog_link_count = 0xa8;       // dialog.entry_link_count
    int dialog_links = 0xac;            // dialog.entry_links
    int dialog_link_index = 0x10;       // dialog.link_index (inside a link)
    int dialog_link_stride = 0x18;      // dialog.link (sizeof row)
    int dialog_text_strref = 0x0c;      // dialog.node_strref (CExoLocString strref)
    int dialog_skippable = 0x3c;        // dialog.skippable (CSWSDialog::field_3c)
                                        // adjudicated k1_steam_103_unpacked binding
                                        // 118 (accept, 0.85): types.h:10377-10404,
                                        // IsDialogDelay 0x4cd2d0 "8b 48 3c" on the
                                        // dialog pointer after the +0x1f4 skip-flag test.

    // CSWGlobalVariableTable: open-hash identifier table.
    // K1 types.h:6133-6151, globalvartables.cpp:7-74; K2 modulus 0x93d.
    int gvt_slot_count = 0x6ef;         // gvt.identifiers size / gvt.identifier size
    int gvt_identifier_stride = 0x18;   // gvt.identifier (sizeof row)
    int gvt_name_len = 0x16;            // gvt.identifier_type_index offset
    int gvt_bool_count = 0xb258;        // gvt.boolean_count
    int gvt_number_count = 0xb25c;      // gvt.number_count
    int gvt_string_count = 0xb264;      // gvt.string_count

    // CSWSJournal {data@+0, size@+4, capacity} at CSWPartyTable+journal.entries;
    // SJournalEntry: K1 types.h:15636-15651 (0x3c, tag +0x18, state +0x20);
    // K2 mac nwsjournal.cpp GetState uses 0x38 / +0x18, state unconfirmed.
    int journal_data = 0;               // journal.data
    int journal_size = 4;               // journal.size
    int journal_entry_stride = 0x3c;    // journal.entry (sizeof row)
    int journal_tag = 0x18;             // journal.entry_tag
    int journal_state = 0x20;           // journal.entry_state

    // CWorldTimer+0x24 timer_paused: K1 types.h:12353-12371.
    int timer_paused = 0x24;            // timer.paused

    // CExoMoviePlayer -> internal (+0) -> movie_playing (+0x30), the fallback
    // when client.is_movie_playing is unresolved. K1 _0040.cpp PlayMoviesAsync.
    int movie_internal = 0;             // movie.internal
    int movie_playing = 0x30;           // movie.playing
};

const Layout& k1_layout();
const Layout& k2_layout();

// ------------------------------------------------------ pure predicates ----
//
// Small and stateless so the integrator can unit-test them without a game.

// The reply-pick acceptance predicate (feasibility facts + RE audit 7):
// dialog active, no selection pending, rows present, the server has no chosen
// reply yet, the owner is not mid-send, and the panel's entry matches the
// server's. Any -1 input means "unknown" and refuses.
inline bool reply_accepted(int dialog_active, int selection_pending, int reply_count,
                           int server_current_reply, int owner_send_pending,
                           int panel_entry, int server_entry) {
    if (dialog_active <= 0 || selection_pending != 0 || reply_count <= 0) return false;
    if (server_current_reply != -1 || owner_send_pending != 0) return false;
    if (panel_entry < 0 || server_entry < 0 || panel_entry != server_entry) return false;
    return true;
}

// The phase table from harness-design.md, with the RE audit's corrections:
// menu is the panel check, gameplay also wants the in-game GUI status, and a
// missing server is menu unless something earlier claims the frame.
inline Phase classify_phase(const PhaseDetail& d, bool have_server, int continue_message_processing,
                            int gui_status, int dialog_active) {
    // No server is the menu, decided before anything else. The menu sits with
    // area_not_ready_to_display == 1, which would otherwise read as Loading,
    // and its load_game_error word is not a reading at all: nothing has written
    // the reentrant stats block yet, so whatever the allocation held is what is
    // there. Only a server makes that word mean something.
    if (!have_server) return Phase::Menu;
    if (d.load_error > 0) return Phase::Error;
    if (continue_message_processing == 1 || d.loading_module == 1 || d.area_not_ready == 1)
        return Phase::Loading;
    if (d.movie == 1) return Phase::Movie;
    // A running server proves simulation, not visible gameplay. Until the
    // menu is actually unlisted, conservatively report Menu even if a native
    // load has completed underneath it (observed on K2 GOG).
    if (d.main_menu == 1) return Phase::Menu;
    if (d.game_over > 0) return Phase::GameOver;
    if (d.input_class == 3 || dialog_active > 0) return Phase::Dialog;
    if (d.pause > 0 && (d.pause & 3) != 0) return Phase::Paused;
    if (d.input_class == 1) return Phase::Minigame;
    if (d.server_mode == 2 && d.input_class == 0) {
        // sw_gui_status: 1 = main interface shown, 2 = hidden for a menu,
        // 3 = hidden temporarily (K1 guiingame.cpp:276-330). Unknown passes.
        if (gui_status == 2 || gui_status == 3) return Phase::Unknown;
        return Phase::Gameplay;
    }
    return Phase::Unknown;
}

// OBJECT_INVALID: what an object id field holds when it names nothing.
constexpr int kInvalidObjectId = 0x7f000000;

// Is a harness-issued load stuck for want of a control object?
//
// The completion block in CClientExoAppInternal::MainLoop
// (clientexoappinternal.cpp:10440-10558) has five gates, and headless the one
// that fails is gate 2: player_creature_id is still OBJECT_INVALID, so the
// client has no creature to look up and the only site that clears
// area_not_ready_to_display (:10988) is never reached. The server is stuck on
// the other side of the same wait -- RunModule's placement loop runs before
// LoadPrimaryPlayer and skipped a player whose CSWSPlayer+0x24 was still 0, so
// nothing sends the ControlObject the client is missing
// (docs/harness-research/critic-re.md, SECOND CORRECTION).
//
// server_mode 2 is what says RunModule has been through: it sets the mode and
// calls LoadPrimaryPlayer inside the same call (serverexoappinternal.cpp:
// 2694-2724), so once the drain sees 2 the player's +0x24 is 1 and the one
// thing the server still wants is the client's AreaLoaded. A -1 input is a
// field this build could not read, and refuses.
inline bool area_loaded_due(int server_mode, int area_not_ready, int player_creature_id,
                            bool have_module) {
    if (server_mode != 2 || area_not_ready != 1 || !have_module) return false;
    return player_creature_id == kInvalidObjectId;
}

// Unknown storage is not evidence of absence; native GUI code may clear this pointer.
inline bool main_menu_pointer_absent(const std::optional<std::uintptr_t>& menu) {
    return menu.has_value() && *menu == 0;
}

// Normal completion must belong to this issued request, not a pre-existing
// running module. The caller captures from-save=1 after its setter, before send.
inline bool normal_load_completed(bool observed_from_save, bool same_server,
                                  int server_mode, bool have_module,
                                  int area_not_ready, int from_save) {
    return observed_from_save && same_server && server_mode == 2 && have_module &&
           area_not_ready == 0 && from_save == 0;
}

// GlobalIndentifier.type_and_index: type in bits 14-15, index in the low 14.
struct GlobalKind { unsigned type; unsigned index; };
inline GlobalKind decode_global_kind(std::uint16_t type_and_index) {
    return {static_cast<unsigned>(type_and_index >> 14),
            static_cast<unsigned>(type_and_index & 0x3fff)};
}

// Booleans are bit-packed most-significant first: globalvartables.cpp:318-362.
inline bool gvt_bool(const std::uint8_t* bools, unsigned idx) {
    return ((bools[idx >> 3] >> (7 - (idx & 7))) & 1) != 0;
}

// Fixed-step increment per SetSnapshotTime is (1e6 / hz * scale_percent) / 100
// in 32-bit int math (_004a.cpp:6336-6371). True when that fits.
inline bool fixed_step_fits(int hz, float scale) {
    if (hz <= 0) return true;
    const double per_tick = 1000000.0 / hz * (scale * 100.0);
    return per_tick < 2147483647.0;
}

// The one GFF read the load path needs: LASTMODULE from savenfo.res, so the
// driver names a save folder and nothing else. Top-level struct only. Returns
// an empty string when the bytes are not a GFF or lack the field.
// Every offset here comes out of the file, so every span is checked by
// subtraction before the addition that would form it: on the -m32 build
// std::size_t is 32 bits and `off + len > size` wraps on a crafted save,
// which is how a truncated file passed validation and then read out of the
// buffer. `span_ok` is the one place that arithmetic lives; the offsets are
// widened to 64 bits so no intermediate sum can wrap either.
inline bool span_ok(std::uint64_t at, std::uint64_t len, std::size_t size) {
    return at <= size && len <= static_cast<std::uint64_t>(size) - at;
}

inline std::string savenfo_last_module(const std::vector<std::uint8_t>& gff) {
    auto u32 = [&](std::uint64_t at, std::uint32_t* out) {
        if (!span_ok(at, 4, gff.size())) return false;
        std::memcpy(out, gff.data() + static_cast<std::size_t>(at), 4);
        return true;
    };
    if (gff.size() < 56) return {};
    std::uint32_t struct_off = 0, struct_cnt = 0, field_off = 0, field_cnt = 0,
                  label_off = 0, label_cnt = 0, data_off = 0, data_cnt = 0,
                  idx_off = 0, idx_cnt = 0;
    if (!u32(8, &struct_off) || !u32(12, &struct_cnt) || !u32(16, &field_off) ||
        !u32(20, &field_cnt) || !u32(24, &label_off) || !u32(28, &label_cnt) ||
        !u32(32, &data_off) || !u32(36, &data_cnt) || !u32(40, &idx_off) || !u32(44, &idx_cnt))
        return {};
    if (struct_cnt == 0) return {};
    const std::uint64_t struct_at = struct_off;
    std::uint32_t s_type = 0, s_data = 0, s_fields = 0;
    if (!u32(struct_at, &s_type) || !u32(struct_at + 4, &s_data) || !u32(struct_at + 8, &s_fields))
        return {};
    if (s_fields > 4096) return {};
    for (std::uint32_t i = 0; i < s_fields; ++i) {
        std::uint32_t field_index = 0;
        if (s_fields == 1) field_index = s_data;
        else if (!u32(static_cast<std::uint64_t>(idx_off) + s_data + static_cast<std::uint64_t>(i) * 4,
                      &field_index))
            return {};
        if (field_index >= field_cnt) return {};
        std::uint32_t f_type = 0, f_label = 0, f_data = 0;
        const std::uint64_t f = static_cast<std::uint64_t>(field_off) +
                                static_cast<std::uint64_t>(field_index) * 12;
        if (!u32(f, &f_type) || !u32(f + 4, &f_label) || !u32(f + 8, &f_data)) return {};
        if (f_label >= label_cnt) return {};
        const std::uint64_t l = static_cast<std::uint64_t>(label_off) +
                                static_cast<std::uint64_t>(f_label) * 16;
        if (!span_ok(l, 16, gff.size())) return {};
        char label[17] = {};
        std::memcpy(label, gff.data() + static_cast<std::size_t>(l), 16);
        std::string name(label);
        for (char& c : name) c = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
        if (name != "LASTMODULE") continue;
        const std::uint64_t at = static_cast<std::uint64_t>(data_off) + f_data;
        if (f_type == 10) {   // CExoString: u32 size, chars
            std::uint32_t n = 0;
            if (!u32(at, &n) || n > 1024 || !span_ok(at + 4, n, gff.size())) return {};
            return std::string(reinterpret_cast<const char*>(gff.data() + static_cast<std::size_t>(at + 4)), n);
        }
        if (f_type == 11) {   // CResRef: u8 size, chars
            if (!span_ok(at, 1, gff.size())) return {};
            const std::uint8_t n = gff[static_cast<std::size_t>(at)];
            if (!span_ok(at + 1, n, gff.size())) return {};
            return std::string(reinterpret_cast<const char*>(gff.data() + static_cast<std::size_t>(at + 1)), n);
        }
        return {};
    }
    return {};
}

// A save's SAVEGAME.sav is an ERF ("MOD V1.0"), and the engine's own load step
// exports its members into GAMEINPROGRESS: before the server reads them:
// CSWGuiSaveLoad::LoadPCAutoSave does it in the open (CreateDirectory2,
// CleanDirectory, CERFFile::Read, ExportFilesFromERF, K1 UN/_006c.cpp:3019-3053).
// The harness does that export itself so no engine function is called with a
// `this` it does not own. Layout: an 8-byte type/version tag, a 9-word header,
// a key list of 16-byte ResRef + u32 ResID + u16 ResType + u16 unused, and a
// resource list of u32 offset + u32 size.
struct SaveErfMember {
    std::string   name;     // "<resref>.<ext>": the file name the engine writes
    std::uint32_t offset;
    std::uint32_t size;
};

// Only the types a save carries. An unknown type is refused rather than
// guessed, because a wrong extension is a file the server silently never
// finds. The four seen in the shipped saves plus rsv, the other type
// LoadModule resolves out of GAMEINPROGRESS: (sav 0x809, rsv 0xbc1 --
// docs/harness-research/fill-load-sequence.md).
inline const char* erf_restype_extension(std::uint16_t type) {
    switch (type) {
        case 0x000: return "res";
        case 0x7eb: return "utc";
        case 0x7f6: return "fac";
        case 0x809: return "sav";
        case 0xbc1: return "rsv";
        default:    return nullptr;
    }
}

// Parse the key and resource lists. False with a reason when the bytes are not
// an ERF the save path produces, so a truncated file reads as a refusal rather
// than as an empty game.
inline bool save_erf_members(const std::vector<std::uint8_t>& erf,
                             std::vector<SaveErfMember>* out, std::string* err) {
    out->clear();
    auto u32 = [&](std::uint64_t at, std::uint32_t* v) {
        if (!span_ok(at, 4, erf.size())) return false;
        std::memcpy(v, erf.data() + static_cast<std::size_t>(at), 4);
        return true;
    };
    if (erf.size() < 44) { *err = "not an ERF: too short"; return false; }
    if (std::memcmp(erf.data(), "MOD ", 4) != 0) { *err = "not a MOD ERF"; return false; }
    std::uint32_t entries = 0, key_off = 0, res_off = 0;
    if (!u32(16, &entries) || !u32(24, &key_off) || !u32(28, &res_off)) {
        *err = "ERF header truncated";
        return false;
    }
    if (entries > 65535) { *err = "ERF entry count out of range"; return false; }
    for (std::uint32_t i = 0; i < entries; ++i) {
        const std::uint64_t k = static_cast<std::uint64_t>(key_off) + static_cast<std::uint64_t>(i) * 24;
        const std::uint64_t r = static_cast<std::uint64_t>(res_off) + static_cast<std::uint64_t>(i) * 8;
        if (!span_ok(k, 24, erf.size()) || !span_ok(r, 8, erf.size())) {
            *err = "ERF lists truncated";
            return false;
        }
        char resref[17] = {};
        std::memcpy(resref, erf.data() + static_cast<std::size_t>(k), 16);
        std::uint16_t type = 0;
        std::memcpy(&type, erf.data() + static_cast<std::size_t>(k) + 20, 2);
        const char* ext = erf_restype_extension(type);
        if (ext == nullptr) {
            char msg[96] = {};
            std::snprintf(msg, sizeof msg, "ERF member '%s' has unmapped restype 0x%x", resref,
                          static_cast<unsigned>(type));
            *err = msg;
            return false;
        }
        SaveErfMember m;
        m.name = std::string(resref) + "." + ext;
        if (!u32(r, &m.offset) || !u32(r + 4, &m.size)) {
            *err = "ERF resource list truncated";
            return false;
        }
        // By subtraction: on the 32-bit build the sum of two u32 read out of the
        // file wraps, and a member at 0xffffff00 with size 0x200 would pass.
        if (!span_ok(m.offset, m.size, erf.size())) {
            *err = "ERF member '" + m.name + "' runs past the file";
            return false;
        }
        out->push_back(std::move(m));
    }
    return true;
}

// ----------------------------------------------------------- the adapter ---
//
// One class for both games. What differs is the Layout and which sites the
// table resolved; the body is in engine_k1.cpp, the K2 parameters in
// engine_k2.cpp.

class GameAdapter final : public EngineAdapter {
public:
    GameAdapter(const char* name, const Layout& layout, const hooks::AddressTable& table,
                std::uintptr_t image_base);

    const char* name() const override { return name_; }
    Phase phase(PhaseDetail* out) override;
    std::string module_name() override;
    Result load_save(const std::string& dir) override;
    Result new_game() override;
    Result chargen_select_class(int index) override;
    Result chargen_begin_play() override;
    std::string chargen_stage() override;
    Result save(int slot, const std::string& name) override;
    Result warp(const std::string& module) override;
    Result dialog(DialogState* out) override;
    Result reply(int visible_index) override;
    Result dialog_continue() override;
    Result dialog_skip() override;
    Result dialog_abort() override;
    Result dialog_clear_sound_wait() override;
    Result clear_auto_pause() override;
    Result set_speed(float scale) override;
    float  speed() const override;
    Result unpause_timers() override;
    Result advance_tutorial() override;
    Result finish_hidden_tutorial() override;
    Result dismiss_status_summary() override;
    Result dismiss_messagebox() override;
    Result equipment_screen(bool visible) override;
    Result door_use(std::uint32_t door_id) override;
    Result door_commit_open(std::uint32_t door_id) override;
    Result door_security(std::uint32_t door_id) override;
    bool take_door_security_result(Result* status, DoorSecurityResult* out) override;
    Result attack(std::uint32_t target_id) override;
    Result dismiss_container() override;
    Result take_all_container() override;
    Result accept_party_selection() override;
    Result set_party_leader(int selector) override;
    bool take_party_leader_result(Result* status, PartyLeaderResult* out) override;
    Result use_item(std::uint32_t item_id, std::uint32_t target_id) override;
    bool take_use_item_result(Result* status, UseItemResult* out) override;
    Result equip_item(std::uint32_t item_id, std::uint32_t slot, bool instant) override;
    bool take_equip_item_result(Result* status, EquipItemResult* out) override;
    Result auto_levelup() override;
    bool take_auto_levelup_result(Result* status, AutoLevelResult* out) override;
    Result after_frame() override;
    Result set_fixed_step(int hz) override;
    Result set_movies(bool enabled) override;
    bool movies_enabled() override;
    Result walk_globals(GlobalsVisitor&) override;
    Result walk_journal(JournalVisitor&) override;
    std::vector<std::string> missing_sites() override;

private:
    // Site lookup. `bound` is a copy taken at construction.
    const Bound* find(const char* site) const;
    bool have(const char* site) const;
    Result require(std::initializer_list<const char*> sites) const;
    // Offset of a field site, or the Layout default when the site is absent.
    // -1 when neither is known. stride() reads a sizeof row's size the same way.
    int off(const char* site, int layout_default) const;
    int stride(const char* site, int layout_default) const;
    unsigned width(const char* site) const;
    // A pointer-valued object reached by a getter call, or by a field on the
    // server internal when the call is unresolved (gvt.table, party.table).
    std::uintptr_t via_call_or_field(const char* call_site, std::uintptr_t call_self,
                                     const char* field_site, std::uintptr_t field_base,
                                     bool field_is_embedded) const;

    // Typed reads through a field site: base + site.offset, site.size wide.
    std::optional<std::int32_t> rd(std::uintptr_t base, const char* site) const;
    std::optional<std::uintptr_t> rd_ptr(std::uintptr_t base, const char* site) const;

    // Engine calls by site name. Return nullopt / false when the site is
    // unresolved; the caller has already required it and reports the name.
    template <typename Ret, typename... Args>
    std::optional<Ret> call(const char* site, void* self, Args... args) const;
    template <typename... Args>
    bool callv(const char* site, void* self, Args... args) const;

    // The g_pAppManager chain.
    std::uintptr_t manager() const;
    std::uintptr_t client_app() const;
    std::uintptr_t client_internal() const;
    std::uintptr_t server_app() const;
    std::uintptr_t server_internal() const;
    std::uintptr_t stats() const;
    std::uintptr_t gui_in_game() const;

    // Server-side conversation state behind the panel's owner id.
    struct ServerDialog {
        std::uintptr_t owner_sws = 0;   // CSWSObject*
        std::uintptr_t dialog = 0;      // CSWSDialog*
        std::uint32_t  owner_sid = 0;   // server object id
    };
    std::optional<ServerDialog> server_dialog(std::uintptr_t panel, std::string* why) const;
    // CGameObject* -> CSWSObject* through the AsSWSObject vtable slot; 0 when
    // the object is not a CSWSObject or the vtable is unreadable.
    std::uintptr_t as_sws_object(std::uintptr_t obj, std::string* why) const;

    bool read_last_module(const std::string& dir, std::string* module, std::string* where) const;
    void apply_speed();
    void log(const char* fmt, ...) const;

    // The AreaLoaded step: armed by load_save, run once per frame from
    // after_frame until it fires or gives up. Never waits for anything.
    void step_load_completion();
    void step_auto_levelup();
    void step_party_leader();
    void step_use_item();
    void step_door_security();
    void step_equip_item();
    Result resolve_player_stats(std::uint32_t* player_id, std::uintptr_t* stats) const;

    // Unlist the main-menu panel once a load has finished, which the GUI path
    // does from the Load Game click the harness never makes.
    bool retire_main_menu();

    // Snapshot CSWGuiManager::panels. It is the engine's authoritative panel
    // list; new_game compares snapshots around OnNewGamePicked rather than
    // guessing a panel from pixels or a vtable address.
    std::vector<std::uintptr_t> gui_panels(std::uintptr_t manager) const;
    Result container_input(const char* action, int event, bool require_take_all);
    bool panel_is_listed(std::uintptr_t manager, std::uintptr_t panel) const;

    // World timers the client and server world clocks live on, in the order
    // load_save step 3 pauses them. Empty when a site did not resolve.
    std::vector<std::uintptr_t> world_timers() const;

    const char*   name_;
    std::string   build_;
    Layout        lay_;
    CallShape     shape_;
    std::uintptr_t delta_ = 0;
    std::unordered_map<std::string, Bound> bound_;
    std::vector<std::string> missing_;
    int fixed_hz_ = 0;

    // The AreaLoaded step's whole state. Armed is "a load is in flight", Sent
    // is "the message went out, watching for the server to place the player",
    // Placed is "the server did, watching for the client's control object".
    // Done and GaveUp are both terminal: this sends at most once per load.
    enum class LoadStep { Idle, Armed, Sent, Placed, Done, GaveUp };
    LoadStep load_step_ = LoadStep::Idle;
    std::chrono::steady_clock::time_point load_sent_at_{};
    std::chrono::steady_clock::time_point load_placed_at_{};
    bool load_control_fallback_sent_ = false;
    bool load_from_save_observed_ = false;
    std::uintptr_t load_server_internal_ = 0;

    // Set only after OnNewGamePicked synchronously adds exactly one real panel
    // to CSWGuiManager::panels. phase() re-checks PanelExists each poll, so a
    // stale pointer becomes chargen=0 rather than a claimed open panel.
    std::uintptr_t new_game_panel_ = 0;
    std::uintptr_t main_char_gen_panel_ = 0;
    enum class ChargenStage { None, Class, Route };
    ChargenStage chargen_stage_ = ChargenStage::None;

    struct PendingAutoLevel {
        bool armed = false;
        bool ready = false;
        int frames = 0;
        std::uint32_t player_id = 0;
        std::uintptr_t stats = 0;
        int level_before = -1;
        std::uint32_t experience = 0;
        Result status = Result::success();
        AutoLevelResult result{};
    } auto_level_;

    struct PendingPartyLeader {
        bool armed = false;
        bool ready = false;
        int frames = 0;
        int selector = 0;
        std::uintptr_t party = 0;
        std::uint32_t leader_before = 0;
        std::uint32_t target_id = 0;
        std::uintptr_t target = 0;
        Result status = Result::success();
        PartyLeaderResult result{};
    } party_leader_;

    struct PendingUseItem {
        bool armed = false;
        bool ready = false;
        int frames = 0;
        std::uintptr_t actor = 0;
        std::uintptr_t target = 0;
        std::uint32_t actor_id = 0;
        std::uint32_t item_id = 0;
        std::uint32_t target_id = 0;
        Result status = Result::success();
        UseItemResult result{};
    } use_item_;

    struct PendingDoorSecurity {
        bool armed = false;
        bool ready = false;
        bool dispatched = false;
        int frames = 0;
        std::uintptr_t party = 0;
        std::uintptr_t actor = 0;
        std::uintptr_t door = 0;
        std::uint32_t actor_id = 0;
        Result status = Result::success();
        DoorSecurityResult result{};
    } door_security_;

    struct PendingEquipItem {
        bool armed = false;
        bool ready = false;
        int frames = 0;
        std::uintptr_t party = 0;
        std::uintptr_t actor = 0;
        std::uintptr_t item = 0;
        std::uint32_t actor_id = 0;
        std::uint32_t item_id = 0;
        std::uint32_t slot = 0;       // public/NWScript slot index
        std::uint32_t slot_mask = 0;  // CSWInventory bit mask
        bool instant = true;
        Result status = Result::success();
        EquipItemResult result{};
    } equip_item_;
};

std::unique_ptr<EngineAdapter> make_k1_adapter(const hooks::AddressTable&, std::uintptr_t image_base);
std::unique_ptr<EngineAdapter> make_k2_adapter(const hooks::AddressTable&, std::uintptr_t image_base);

// Every logical site name an adapter may ask for, so missing_sites() is a
// complete answer rather than a running total. Defined in engine_k1.cpp.
const std::vector<const char*>& adapter_site_names();

}  // namespace kp::harness
