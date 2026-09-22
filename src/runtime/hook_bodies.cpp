// The hook bodies: RunScript, MainLoop, DoConsole, ten EventHandlers, save/load.
//
// Signatures come from the recovered C for these specific functions, one per
// site, and they are the thing in this file that must not be edited casually:
// __thiscall is callee-cleans, so a body that pops a different number of bytes
// than the function it replaced skews ESP on that thread permanently, and the
// crash lands somewhere unrelated hours later. See hooks/thiscall.hpp.
//
//   K1 0x005D45D0  int  __thiscall CVirtualMachineInternal::RunScript(
//                          CExoString* name, uint32_t objectId, int hasObject)
//   K1 0x004BABB0  void* __thiscall CServerExoAppInternal::MainLoop()
//   K1 0x00401F00  void __cdecl DoConsole(char c)
//
// Every body has the same shape, and the shape is the safety argument:
//
//   1. If we are not live, or this site is poisoned, forward to the original
//      and do nothing else. This is the resting state after a fault and during
//      startup, and it makes the game behave exactly as it would unpatched.
//   2. Do our work inside a nested scope with a fault guard armed.
//   3. Leave that scope, THEN call the original. A fault inside game code is
//      the game's business and must not be claimed by us.
#include <atomic>
#include <bit>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <fstream>
#include <string>
#include <vector>

#include "api/timers.hpp"
#include "api/output.hpp"
#include "events/contract.hpp"
#include "events/payload.hpp"
#include "events/situation.hpp"
#include "events/table.hpp"
#include "harness/commands.hpp"
#include "harness/engine.hpp"
#include "harness/ring.hpp"
#include "hooks/registry.hpp"
#include "hooks/thiscall.hpp"
#include "lua/host.hpp"
#include "lua/value.hpp"
#include "platform/platform.hpp"
#include "runtime/internal.hpp"
#include "runtime/runtime.hpp"
#include "version.hpp"

extern "C" {
#include "lauxlib.h"
#include "lua.h"
#include "lualib.h"
}

namespace kp::runtime {
namespace {

// The engine's string: a pointer and an explicit length. NOT NUL-terminated by
// contract, which is why nothing here calls strlen on it.
struct CExoString {
    char*         c_string;
    std::uint32_t length;
};
static_assert(sizeof(CExoString) == 8, "CExoString is two 32-bit fields");

// A script name is a ResRef-ish thing; anything past this is a wild pointer
// that happened to land on plausible bytes, not a string.
constexpr std::uint32_t kMaxEngineString = 64 * 1024;

std::string read_exostring(const CExoString* s) {
    // The pointer came out of the engine through a patched prologue. It is
    // almost always fine, and "almost always" is exactly the case that has to
    // be probed rather than trusted -- the fault guard can recover from reading
    // it, but a refusal is cheaper and loses nothing.
    if (s == nullptr || !platform::is_readable(s, sizeof *s)) return {};
    if (s->c_string == nullptr || s->length == 0 || s->length > kMaxEngineString) return {};
    if (!platform::is_readable(s->c_string, s->length)) return {};

    // Verified live: RunScript's script-name CExoString reports length 17 for
    // "k_def_attacked01" (16 real characters) -- the engine's length INCLUDES a
    // trailing NUL for this particular string, contrary to the "not NUL-
    // terminated by contract" comment above, which held for every other
    // CExoString this runtime reads but not for this one. The embedded NUL
    // survived into the Lua string unnoticed because it prints identically to
    // the clean name in a terminal; every `script_name == "..."` comparison in
    // every script silently failed until this was found by hex-dumping the
    // bytes. Strip exactly one trailing NUL, and only a NUL -- anything else at
    // that position is real content, not a terminator, and must not be eaten.
    std::uint32_t len = s->length;
    if (len > 0 && s->c_string[len - 1] == '\0') --len;
    return std::string(s->c_string, len);
}

// ------------------------------------------------------- site-local state ---

std::atomic<void*> g_orig_run_script{nullptr};
std::atomic<void*> g_orig_main_loop{nullptr};
std::atomic<void*> g_orig_do_console{nullptr};
std::atomic<void*> g_orig_creature{nullptr};
std::atomic<void*> g_orig_door{nullptr};
std::atomic<void*> g_orig_placeable{nullptr};
std::atomic<void*> g_orig_trigger{nullptr};
std::atomic<void*> g_orig_module{nullptr};
std::atomic<void*> g_orig_area{nullptr};
std::atomic<void*> g_orig_encounter{nullptr};
std::atomic<void*> g_orig_aoe{nullptr};
std::atomic<void*> g_orig_store{nullptr};
std::atomic<void*> g_orig_waypoint{nullptr};
std::atomic<void*> g_orig_save{nullptr};
std::atomic<void*> g_orig_load{nullptr};
std::atomic<void*> g_orig_client_loop{nullptr};
std::atomic<void*> g_orig_move_to_point{nullptr};
std::atomic<void*> g_orig_net_start_connect{nullptr};
std::atomic<void*> g_orig_net_start_server{nullptr};
std::atomic<void*> g_orig_net_send{nullptr};
std::atomic<void*> g_orig_net_process{nullptr};
std::atomic<void*> g_orig_client_area_get_server_area{nullptr};
std::atomic<void*> g_orig_add_move_to_point{nullptr};
std::atomic<void*> g_server_net{nullptr};
std::atomic<void*> g_client_net{nullptr};
std::atomic<void*> g_client_support_server_net{nullptr};
std::atomic<std::uint32_t> g_net_destination_offset{0};
std::atomic<std::uint32_t> g_net_outbound_frames{0};
std::atomic<std::uint32_t> g_net_inbound_frames{0};

std::atomic<bool> g_poison_run_script{false};
std::atomic<bool> g_poison_client_area_get_server_area{false};
std::atomic<bool> g_poison_add_move_to_point{false};
std::atomic<bool> g_poison_main_loop{false};
std::atomic<bool> g_poison_do_console{false};
// One flag per event site, not one shared flag: a fault in the door handler
// used to poison creature/placeable/trigger/... too, taking all ten dark for
// one site's bug.
std::atomic<bool> g_poison_event_creature{false};
std::atomic<bool> g_poison_event_door{false};
std::atomic<bool> g_poison_event_placeable{false};
std::atomic<bool> g_poison_event_trigger{false};
std::atomic<bool> g_poison_event_module{false};
std::atomic<bool> g_poison_event_area{false};
std::atomic<bool> g_poison_event_encounter{false};
std::atomic<bool> g_poison_event_aoe{false};
std::atomic<bool> g_poison_event_store{false};
std::atomic<bool> g_poison_event_waypoint{false};
std::atomic<bool> g_poison_save{false};
std::atomic<bool> g_poison_load{false};
std::atomic<bool> g_poison_move_to_point{false};
std::atomic<unsigned> g_tick_scale{1};
std::atomic<std::uint64_t> g_client_loop_frames{0};

std::string g_situation_path;
std::string g_situation_blob;

using RunScriptFn = int (KP_THISCALL*)(void*, CExoString*, std::uint32_t, int);
#if defined(_WIN32)
#define KP_SERVER_LOOP_CC KP_THISCALL
#else
#define KP_SERVER_LOOP_CC __attribute__((cdecl))
#endif
using MainLoopFn  = void* (KP_SERVER_LOOP_CC*)(void*);
using DoConsoleFn = void (__attribute__((cdecl)) *)(char);

// The client loop's convention is a platform fact, not a per-site one. The
// DLL only ever runs inside the MSVC-built PE, where every method is
// __thiscall; the .so only ever runs inside the GCC-built kotor2 ELF, where
// `this` is the first stack argument. Verified against the ELF prologue at
// the resolved site: push ebp/ebx/edi/esi; sub esp; mov ebp,[esp+0xd0].
//
//   K1 0x00602EB0  int __thiscall CClientExoAppInternal::MainLoop()
//
// The server-loop body above still assumes __thiscall on both; that is the
// same latent mismatch on the ELF and is left for the K2 native work.
#if defined(_WIN32)
#define KP_CLIENT_LOOP_CC KP_THISCALL
#else
#define KP_CLIENT_LOOP_CC __attribute__((cdecl))
#endif
using ClientLoopFn = int (KP_CLIENT_LOOP_CC*)(void*);
using ClientFrameWrapperFn = int (__attribute__((cdecl)) *)(void*);
std::atomic<void*> g_orig_client_frame_wrapper{nullptr};

// CSWSCreature::AIActionMoveToPoint(this, CSWSObjectActionNode*): K1
// servercore/nwscreatureai.cpp:26604.  The first four branches are the
// complete admission gate before the action node is consumed.  We observe
// them here and always forward the original call unmodified.
using MoveToPointFn = int (KP_THISCALL*)(void*, void*);

// K1 GOG and K2 GOG machine-code ABIs. Both exact images use these callee-pop
// shapes; the final stack word on SendMessageToPlayer and StartServerMode is
// absent from advisory prototypes but required by their observed ret 0x10 and
// ret 8 instructions.
using NetStartConnectFn = int (KP_THISCALL*)(void*, std::uint32_t, CExoString*, CExoString*,
                                             std::uint32_t, std::uint32_t);
using NetStartServerFn = int (KP_THISCALL*)(void*, CExoString*, std::uint32_t);
using NetSendFn = int (KP_THISCALL*)(void*, std::uint32_t, char*, int, std::uint32_t);
using NetProcessFn = void (KP_THISCALL*)(void*, int);
using NoArgPointerFn = void* (KP_THISCALL*)(void*);
using OnePointerVoidFn = void (KP_THISCALL*)(void*, void*);
struct Vector3 { float x, y, z; };
using AddMoveToPointFn = int (KP_THISCALL*)(void*, std::uint16_t, Vector3*,
    std::uint32_t, std::uint32_t, int, float, float, int, int, int, int, int, int,
    Vector3*, std::uint32_t, std::uint32_t, int);
using GetPlayerCreatureIdFn = std::uint32_t (KP_THISCALL*)(void*);
using GetGameObjectFn = void* (KP_THISCALL*)(void*, std::uint32_t);
using SetPositionFn = void (KP_THISCALL*)(void*, Vector3*, int, int, int);

void append_wire_u32(std::vector<std::uint8_t>& out, std::uint32_t value) {
    out.push_back(static_cast<std::uint8_t>(value >> 24));
    out.push_back(static_cast<std::uint8_t>(value >> 16));
    out.push_back(static_cast<std::uint8_t>(value >> 8));
    out.push_back(static_cast<std::uint8_t>(value));
}

bool take_wire_u32(const std::vector<std::uint8_t>& in, std::size_t& at,
                   std::uint32_t& value) {
    if (at + 4 > in.size()) return false;
    value = (static_cast<std::uint32_t>(in[at]) << 24) |
            (static_cast<std::uint32_t>(in[at + 1]) << 16) |
            (static_cast<std::uint32_t>(in[at + 2]) << 8) |
            static_cast<std::uint32_t>(in[at + 3]);
    at += 4;
    return true;
}

void append_wire_float(std::vector<std::uint8_t>& out, float value) {
    append_wire_u32(out, std::bit_cast<std::uint32_t>(value));
}

bool take_wire_float(const std::vector<std::uint8_t>& in, std::size_t& at, float& value) {
    std::uint32_t bits = 0;
    if (!take_wire_u32(in, at, bits)) return false;
    value = std::bit_cast<float>(bits);
    return true;
}

bool valid_position(const Vector3& value) {
    return std::isfinite(value.x) && std::isfinite(value.y) && std::isfinite(value.z) &&
           std::abs(value.x) <= 1000000.0f && std::abs(value.y) <= 1000000.0f &&
           std::abs(value.z) <= 1000000.0f;
}

void* current_server_app() {
    const hooks::AddressTable* table = Runtime::instance().table();
    const hooks::Site* manager_site = table != nullptr ? table->find("g.app_manager") : nullptr;
    const hooks::Site* server_field = table != nullptr ? table->find("appmgr.server") : nullptr;
    if (manager_site == nullptr || !manager_site->resolved || server_field == nullptr ||
        !server_field->resolved) return nullptr;
    std::uint32_t manager = 0, server = 0;
    const void* manager_at = reinterpret_cast<const void*>(manager_site->addr + manager_site->offset);
    if (!platform::is_readable(manager_at, sizeof manager)) return nullptr;
    std::memcpy(&manager, manager_at, sizeof manager);
    const void* server_at = reinterpret_cast<const void*>(
        static_cast<std::uintptr_t>(manager) + server_field->offset);
    if (manager == 0 || !platform::is_readable(server_at, sizeof server)) return nullptr;
    std::memcpy(&server, server_at, sizeof server);
    return reinterpret_cast<void*>(static_cast<std::uintptr_t>(server));
}

bool replay_move_to_point(const multiplayer::Frame& frame) {
    if (frame.kind != multiplayer::FrameKind::MoveToPoint ||
        frame.sender != multiplayer::FrameSender::Client ||
        Runtime::instance().role() != multiplayer::Role::Server) return false;
    const hooks::AddressTable* table = Runtime::instance().table();
    const hooks::Site* get_player = table != nullptr
        ? table->find("server.get_player_creature_id") : nullptr;
    const hooks::Site* get_object = table != nullptr ? table->find("server.get_game_object") : nullptr;
    const hooks::Site* set_position = table != nullptr
        ? table->find("server_object.set_position") : nullptr;
    void* server = current_server_app();
    if (server == nullptr || get_player == nullptr || !get_player->resolved ||
        get_object == nullptr || !get_object->resolved || set_position == nullptr ||
        !set_position->resolved) return true;

    std::size_t at = 0;
    std::uint32_t creature_id = 0, action = 0, p3 = 0, p4 = 0, p5 = 0, p8 = 0,
        p9 = 0, p10 = 0, p11 = 0, p12 = 0, p13 = 0, p15 = 0, p16 = 0, p17 = 0;
    Vector3 destination{}, secondary{};
    float p6 = 0, p7 = 0;
    const bool decoded = take_wire_u32(frame.payload, at, creature_id) &&
        take_wire_u32(frame.payload, at, action) &&
        take_wire_float(frame.payload, at, destination.x) &&
        take_wire_float(frame.payload, at, destination.y) &&
        take_wire_float(frame.payload, at, destination.z) &&
        take_wire_u32(frame.payload, at, p3) && take_wire_u32(frame.payload, at, p4) &&
        take_wire_u32(frame.payload, at, p5) && take_wire_float(frame.payload, at, p6) &&
        take_wire_float(frame.payload, at, p7) && take_wire_u32(frame.payload, at, p8) &&
        take_wire_u32(frame.payload, at, p9) && take_wire_u32(frame.payload, at, p10) &&
        take_wire_u32(frame.payload, at, p11) && take_wire_u32(frame.payload, at, p12) &&
        take_wire_u32(frame.payload, at, p13) && take_wire_float(frame.payload, at, secondary.x) &&
        take_wire_float(frame.payload, at, secondary.y) &&
        take_wire_float(frame.payload, at, secondary.z) && take_wire_u32(frame.payload, at, p15) &&
        take_wire_u32(frame.payload, at, p16) && take_wire_u32(frame.payload, at, p17) &&
        at == frame.payload.size();
    const std::uint32_t player_id = reinterpret_cast<GetPlayerCreatureIdFn>(get_player->addr)(server);
    if (!decoded || !valid_position(destination) || !valid_position(secondary) ||
        !std::isfinite(p6) || !std::isfinite(p7) || creature_id != player_id) {
        Runtime::instance().log("multiplayer: rejected MoveToPoint actor %u (player %u)",
                                creature_id, player_id);
        return true;
    }
    void* creature = reinterpret_cast<GetGameObjectFn>(get_object->addr)(server, player_id);
    if (creature == nullptr) return true;
    // ponytail: the dedicated loop cannot safely advance retail pathfinding
    // without a local playing client. Apply the validated destination through
    // the engine's own area-indexing setter; replace this with input simulation
    // once the headless AI loop is independently brought up.
    reinterpret_cast<SetPositionFn>(set_position->addr)(creature, &destination, 1, 1, 0);
    Runtime::instance().log("multiplayer: replayed MoveToPoint for %u to %.3f %.3f %.3f",
                            player_id, destination.x, destination.y, destination.z);
    std::vector<std::uint8_t> authoritative;
    authoritative.reserve(16);
    append_wire_u32(authoritative, player_id);
    append_wire_float(authoritative, destination.x);
    append_wire_float(authoritative, destination.y);
    append_wire_float(authoritative, destination.z);
    if (multiplayer::Transport* transport = active_multiplayer_transport();
        transport != nullptr &&
        !transport->send(authoritative, 0, 0,
                         multiplayer::FrameKind::AuthoritativePosition))
        Runtime::instance().log("multiplayer: failed to acknowledge position for %u", player_id);
    return true;
}

bool replay_authoritative_position(const multiplayer::Frame& frame) {
    if (frame.kind != multiplayer::FrameKind::AuthoritativePosition ||
        frame.sender != multiplayer::FrameSender::Server ||
        Runtime::instance().role() != multiplayer::Role::Client) return false;
    const hooks::AddressTable* table = Runtime::instance().table();
    const hooks::Site* get_player = table != nullptr
        ? table->find("server.get_player_creature_id") : nullptr;
    const hooks::Site* get_object = table != nullptr ? table->find("server.get_game_object") : nullptr;
    const hooks::Site* set_position = table != nullptr
        ? table->find("server_object.set_position") : nullptr;
    void* server = current_server_app();
    if (server == nullptr || get_player == nullptr || !get_player->resolved ||
        get_object == nullptr || !get_object->resolved || set_position == nullptr ||
        !set_position->resolved) return true;

    std::size_t at = 0;
    std::uint32_t creature_id = 0;
    Vector3 position{};
    const bool decoded = take_wire_u32(frame.payload, at, creature_id) &&
        take_wire_float(frame.payload, at, position.x) &&
        take_wire_float(frame.payload, at, position.y) &&
        take_wire_float(frame.payload, at, position.z) && at == frame.payload.size();
    const std::uint32_t player_id = reinterpret_cast<GetPlayerCreatureIdFn>(get_player->addr)(server);
    if (!decoded || !valid_position(position) || creature_id != player_id) {
        Runtime::instance().log("multiplayer: rejected authoritative position actor %u (player %u)",
                                creature_id, player_id);
        return true;
    }
    void* creature = reinterpret_cast<GetGameObjectFn>(get_object->addr)(server, player_id);
    if (creature == nullptr) return true;
    reinterpret_cast<SetPositionFn>(set_position->addr)(creature, &position, 1, 1, 0);
    Runtime::instance().log(
        "multiplayer: applied authoritative position for %u at %.3f %.3f %.3f",
        player_id, position.x, position.y, position.z);
    return true;
}

void* multiplayer_endpoint() {
    return Runtime::instance().role() == multiplayer::Role::Server
        ? g_server_net.load(std::memory_order_acquire)
        : g_client_net.load(std::memory_order_acquire);
}

void trace_multiplayer_frame(const char* direction, std::uint32_t ordinal,
                             std::uint32_t player, const std::uint8_t* bytes,
                             std::size_t length, bool accepted) {
    // ponytail: the first 128 frames are enough to diagnose bootstrap ordering
    // without turning the runtime log into an unbounded packet capture.
    if (ordinal > 128) return;
    const unsigned b0 = length > 0 ? bytes[0] : 0;
    const unsigned b1 = length > 1 ? bytes[1] : 0;
    const unsigned b2 = length > 2 ? bytes[2] : 0;
    const unsigned b3 = length > 3 ? bytes[3] : 0;
    const unsigned b7 = length > 7 ? bytes[7] : 0;
    const unsigned b8 = length > 8 ? bytes[8] : 0;
    Runtime::instance().log(
        "multiplayer: %s #%u player=%u length=%zu head=%02x%02x%02x%02x b7=%02x b8=%02x %s",
        direction, ordinal, player, length, b0, b1, b2, b3, b7, b8,
        accepted ? "accepted" : "rejected");
}

int KP_THISCALL net_start_connect_body(void* self, std::uint32_t player,
                                       CExoString* name, CExoString* password,
                                       std::uint32_t timeout, std::uint32_t flags) {
    auto orig = reinterpret_cast<NetStartConnectFn>(
        g_orig_net_start_connect.load(std::memory_order_acquire));
    if (active_multiplayer_transport() != nullptr &&
        Runtime::instance().role() == multiplayer::Role::Client) {
        g_client_net.store(self, std::memory_order_release);
        Runtime::instance().log("multiplayer: captured client network endpoint %p", self);
    }
    return orig != nullptr ? orig(self, player, name, password, timeout, flags) : 0;
}

int KP_THISCALL net_start_server_mode_body(void* self, CExoString* name,
                                            std::uint32_t extra) {
    auto orig = reinterpret_cast<NetStartServerFn>(
        g_orig_net_start_server.load(std::memory_order_acquire));
    if (active_multiplayer_transport() != nullptr) {
        if (Runtime::instance().role() == multiplayer::Role::Server) {
            g_server_net.store(self, std::memory_order_release);
            Runtime::instance().log("multiplayer: captured server network endpoint %p", self);
        } else if (Runtime::instance().role() == multiplayer::Role::Client) {
            g_client_support_server_net.store(self, std::memory_order_release);
            Runtime::instance().log("multiplayer: captured client support-server endpoint %p", self);
        }
    }
    return orig != nullptr ? orig(self, name, extra) : 0;
}

int KP_THISCALL add_move_to_point_body(
    void* creature, std::uint16_t action, Vector3* destination,
    std::uint32_t p3, std::uint32_t p4, int p5, float p6, float p7, int p8, int p9,
    int p10, int p11, int p12, int p13, Vector3* secondary, std::uint32_t p15,
    std::uint32_t p16, int p17) {
    auto orig = reinterpret_cast<AddMoveToPointFn>(
        g_orig_add_move_to_point.load(std::memory_order_acquire));
    multiplayer::Transport* transport = active_multiplayer_transport();
    if (transport != nullptr && Runtime::instance().role() == multiplayer::Role::Client &&
        !g_poison_add_move_to_point.load(std::memory_order_acquire)) {
        KP_HOOK_GUARD_BEGIN("creature.add_move_to_point_action", g_poison_add_move_to_point, {})
        const hooks::AddressTable* table = Runtime::instance().table();
        const hooks::Site* get_player = table != nullptr
            ? table->find("server.get_player_creature_id") : nullptr;
        const hooks::Site* object_id = table != nullptr ? table->find("object.id") : nullptr;
        void* server = current_server_app();
        std::uint32_t creature_id = 0;
        if (server != nullptr && get_player != nullptr && get_player->resolved &&
            object_id != nullptr && object_id->resolved && destination != nullptr &&
            secondary != nullptr && platform::is_readable(destination, sizeof *destination) &&
            platform::is_readable(secondary, sizeof *secondary) &&
            platform::is_readable(reinterpret_cast<const std::uint8_t*>(creature) +
                                  object_id->offset, sizeof creature_id)) {
            std::memcpy(&creature_id, reinterpret_cast<const std::uint8_t*>(creature) +
                                      object_id->offset, sizeof creature_id);
            const std::uint32_t player_id =
                reinterpret_cast<GetPlayerCreatureIdFn>(get_player->addr)(server);
            if (creature_id == player_id) {
                std::vector<std::uint8_t> payload;
                payload.reserve(88);
                append_wire_u32(payload, creature_id);
                append_wire_u32(payload, action);
                append_wire_float(payload, destination->x);
                append_wire_float(payload, destination->y);
                append_wire_float(payload, destination->z);
                append_wire_u32(payload, p3); append_wire_u32(payload, p4);
                append_wire_u32(payload, static_cast<std::uint32_t>(p5));
                append_wire_float(payload, p6); append_wire_float(payload, p7);
                for (const int value : {p8, p9, p10, p11, p12, p13})
                    append_wire_u32(payload, static_cast<std::uint32_t>(value));
                append_wire_float(payload, secondary->x);
                append_wire_float(payload, secondary->y);
                append_wire_float(payload, secondary->z);
                append_wire_u32(payload, p15); append_wire_u32(payload, p16);
                append_wire_u32(payload, static_cast<std::uint32_t>(p17));
                if (transport->send(payload, 0, 0, multiplayer::FrameKind::MoveToPoint))
                    Runtime::instance().log(
                        "multiplayer: sent MoveToPoint for %u to %.3f %.3f %.3f",
                        creature_id, destination->x, destination->y, destination->z);
            }
        }
        KP_HOOK_GUARD_END
    }
    return orig != nullptr ? orig(creature, action, destination, p3, p4, p5, p6, p7,
                                  p8, p9, p10, p11, p12, p13, secondary, p15, p16, p17) : 0;
}

int KP_THISCALL net_send_message_body(void* self, std::uint32_t player, char* message,
                                      int length, std::uint32_t extra) {
    auto orig = reinterpret_cast<NetSendFn>(g_orig_net_send.load(std::memory_order_acquire));
    multiplayer::Transport* transport = active_multiplayer_transport();
    if (transport != nullptr && Runtime::instance().role() == multiplayer::Role::Client &&
        self == g_client_support_server_net.load(std::memory_order_acquire))
        return 1;
    if (transport == nullptr || self != multiplayer_endpoint())
        return orig != nullptr ? orig(self, player, message, length, extra) : 0;

    if (length < 2 || static_cast<std::size_t>(length) > multiplayer::kMaxFrameBytes ||
        message == nullptr || !platform::is_readable(message, static_cast<std::size_t>(length))) {
        Runtime::instance().log("multiplayer: rejected outbound frame length %d", length);
        return 0;
    }
    const auto* bytes = reinterpret_cast<const std::uint8_t*>(message);
    const bool sent = transport->send({bytes, static_cast<std::size_t>(length)}, player, extra);
    // The client UI still dereferences CServerExoApp state even when the
    // authoritative server lives in another process (InitializeMap is one
    // example).  Keep the client process' support server populated by feeding
    // it the same requests through the stock paired net layer.  Its outbound
    // messages are suppressed above, so only the remote server can drive the
    // visible client.
    const bool mirrored = Runtime::instance().role() != multiplayer::Role::Client ||
        g_client_support_server_net.load(std::memory_order_acquire) == nullptr ||
        (orig != nullptr && orig(self, player, message, length, extra) != 0);
    trace_multiplayer_frame("outbound",
        g_net_outbound_frames.fetch_add(1, std::memory_order_relaxed) + 1,
        player, bytes, static_cast<std::size_t>(length), sent && mirrored);
    return sent && mirrored ? 1 : 0;
}

void KP_THISCALL net_process_frames_body(void* self, int process) {
    auto orig = reinterpret_cast<NetProcessFn>(g_orig_net_process.load(std::memory_order_acquire));
    auto enqueue = reinterpret_cast<NetSendFn>(g_orig_net_send.load(std::memory_order_acquire));
    multiplayer::Transport* transport = active_multiplayer_transport();
    const std::uint32_t destination_offset =
        g_net_destination_offset.load(std::memory_order_acquire);
    if (process != 0 && transport != nullptr && self == multiplayer_endpoint() &&
        enqueue != nullptr && destination_offset != 0) {
        hooks::guard_void([&] {
            std::vector<multiplayer::Frame> frames;
            // ponytail: 64 frames per engine pass bounds tick latency; raise it
            // only after a measured throughput bottleneck.
            transport->take_frames(64, frames);
            const multiplayer::FrameSender expected = Runtime::instance().role() ==
                multiplayer::Role::Server ? multiplayer::FrameSender::Client
                                          : multiplayer::FrameSender::Server;
            std::uint32_t peer_address = 0;
            const auto* destination = reinterpret_cast<const std::uint8_t*>(self) +
                destination_offset;
            if (platform::is_readable(destination, sizeof peer_address))
                std::memcpy(&peer_address, destination, sizeof peer_address);
            std::vector<std::uint8_t> synthetic_peer;
            void* peer = reinterpret_cast<void*>(static_cast<std::uintptr_t>(peer_address));
            if (peer == nullptr && !frames.empty()) {
                // A split client intentionally has no in-process server peer.
                // SendMessageToPlayer reads only this one field from its
                // sender, so a minimal synthetic sender lets the original
                // function enqueue into the real client ring unchanged.
                synthetic_peer.resize(destination_offset + sizeof peer_address);
                const std::uint32_t self_address = static_cast<std::uint32_t>(
                    reinterpret_cast<std::uintptr_t>(self));
                std::memcpy(synthetic_peer.data() + destination_offset,
                            &self_address, sizeof self_address);
                peer = synthetic_peer.data();
            }
            for (multiplayer::Frame& frame : frames) {
                if (replay_move_to_point(frame)) continue;
                if (replay_authoritative_position(frame)) continue;
                if (frame.sender != expected || frame.payload.size() < 2 ||
                    frame.kind != multiplayer::FrameKind::Engine ||
                    frame.payload.size() > multiplayer::kMaxFrameBytes || peer == nullptr ||
                    !platform::is_readable(reinterpret_cast<const std::uint8_t*>(peer) +
                                           destination_offset, sizeof peer_address)) {
                    Runtime::instance().log("multiplayer: rejected inbound frame length %zu",
                                            frame.payload.size());
                    continue;
                }
                // Feed the paired endpoint's original sender. It copies into
                // `self` using the stock bounded ring; the original process
                // call below then performs native BNCS/BNCR/game dispatch.
                const int queued = enqueue(peer, frame.player,
                    reinterpret_cast<char*>(frame.payload.data()),
                    static_cast<int>(frame.payload.size()), frame.extra);
                trace_multiplayer_frame("inbound",
                    g_net_inbound_frames.fetch_add(1, std::memory_order_relaxed) + 1,
                    frame.player, frame.payload.data(), frame.payload.size(), queued != 0);
            }
        });
    }
    if (orig != nullptr) orig(self, process);
}

void* KP_THISCALL client_area_get_server_area_body(void* self) {
    auto orig = reinterpret_cast<NoArgPointerFn>(
        g_orig_client_area_get_server_area.load(std::memory_order_acquire));
    void* area = orig != nullptr ? orig(self) : nullptr;
    if (area != nullptr || active_multiplayer_transport() == nullptr ||
        Runtime::instance().role() != multiplayer::Role::Client ||
        g_poison_client_area_get_server_area.load(std::memory_order_acquire))
        return area;

    void* fallback = nullptr;
    KP_HOOK_GUARD_BEGIN("client.area_get_server_area",
                        g_poison_client_area_get_server_area, fallback = nullptr)
    const hooks::AddressTable* table = Runtime::instance().table();
    const hooks::Site* manager_site = table != nullptr ? table->find("g.app_manager") : nullptr;
    const hooks::Site* server_field = table != nullptr ? table->find("appmgr.server") : nullptr;
    const hooks::Site* get_module = table != nullptr ? table->find("app.get_module") : nullptr;
    const hooks::Site* get_area = table != nullptr ? table->find("module.get_area") : nullptr;
    const hooks::Site* attach_client = table != nullptr
        ? table->find("client_area.attach_from_server") : nullptr;
    const hooks::Site* attach_server = table != nullptr
        ? table->find("server_area.attach_from_client") : nullptr;
    if (manager_site != nullptr && manager_site->resolved &&
        server_field != nullptr && server_field->resolved &&
        get_module != nullptr && get_module->resolved &&
        get_area != nullptr && get_area->resolved &&
        attach_client != nullptr && attach_client->resolved &&
        attach_server != nullptr && attach_server->resolved) {
        std::uint32_t manager = 0;
        const auto manager_at = reinterpret_cast<const void*>(
            manager_site->addr + manager_site->offset);
        if (platform::is_readable(manager_at, sizeof manager))
            std::memcpy(&manager, manager_at, sizeof manager);
        std::uint32_t server = 0;
        const auto server_at = reinterpret_cast<const void*>(
            static_cast<std::uintptr_t>(manager) + server_field->offset);
        if (manager != 0 && platform::is_readable(server_at, sizeof server))
            std::memcpy(&server, server_at, sizeof server);
        if (server != 0) {
            void* module = reinterpret_cast<NoArgPointerFn>(get_module->addr)(
                reinterpret_cast<void*>(static_cast<std::uintptr_t>(server)));
            if (module != nullptr) {
                fallback = reinterpret_cast<NoArgPointerFn>(get_area->addr)(module);
                if (fallback != nullptr) {
                    reinterpret_cast<OnePointerVoidFn>(attach_server->addr)(fallback, self);
                    reinterpret_cast<OnePointerVoidFn>(attach_client->addr)(self, fallback);
                }
            }
        }
    }
    KP_HOOK_GUARD_END

    if (fallback != nullptr) {
        static std::atomic<bool> logged{false};
        if (!logged.exchange(true, std::memory_order_relaxed))
            Runtime::instance().log(
                "multiplayer: client area id has no support-server mapping; using active support area");
    }
    return fallback;
}

// Server tick for the event ring: the host counts server frames, and the
// ring records are keyed to that so a driver can line events up with ticks.
std::uint64_t ring_tick(lua::Host* host) { return host != nullptr ? host->tick() : 0; }

// An argument list built to whatever shape the contract declares, matched by
// name. Used for events whose contract this code does not get to assume --
// if the table gains OnRunScriptDone with a different argument list, this
// fills what it can and passes none for the rest rather than pushing the
// wrong things in the wrong order.
struct NamedArg {
    const char* name;
    lua::Value  value;
};

std::vector<lua::Value> shape_args(const events::EventContract& ev,
                                   const std::vector<NamedArg>& have) {
    std::vector<lua::Value> out;
    out.reserve(ev.args.size());
    for (const events::Argument& want : ev.args) {
        const lua::Value* found = nullptr;
        for (const NamedArg& h : have)
            if (want.name == h.name) { found = &h.value; break; }
        out.push_back(found != nullptr ? *found : lua::Value::none());
    }
    return out;
}

void dispatch_run_script_done(lua::Host& host, const std::string& script_name,
                              std::uint32_t object_id, int has_object, bool ran,
                              bool blocked, const events::Outcome& outcome) {
    const events::EventContract* done = find_contract("OnRunScriptDone");
    if (done == nullptr) return;
    const std::vector<NamedArg> have = {
        {"script_name", lua::Value::str(script_name)},
        {"object_id", lua::Value::object(object_id)},
        {"has_object", lua::Value::integer(has_object)},
        {"ran", lua::Value::boolean(ran)},
        {"blocked", lua::Value::boolean(blocked)},
        {"claimed_by", lua::Value::str(outcome.claimed_by)},
    };
    host.dispatch(*done, shape_args(*done, have));
}

// ------------------------------------------------------------- RunScript ----

// The blocking decision, separated so the guarded region has one job.
struct ScriptVerdict {
    bool block = false;
    int  engine_result = 1;
};

ScriptVerdict decide(const events::EventContract& ev, const events::Outcome& outcome) {
    const events::BlockVerdict b = events::blocking_verdict(ev, outcome);
    return {b.skip_original, b.engine_result};
}

// `self` is the CVirtualMachineInternal, which is the only place the two live
// VM objects the routine bridge needs can be reached from. Revalidate the
// cached context; a later script can repair an invalidated VM binding.
int KP_THISCALL run_script_body(void* self, CExoString* name, std::uint32_t object_id,
                                int has_object) {
    capture_vm(self);

    auto orig = reinterpret_cast<RunScriptFn>(g_orig_run_script.load(std::memory_order_acquire));

    // One load, used for the whole call. Reading the published pointer twice
    // would let it be null on the second read, which is the bug the check was
    // there to prevent.
    lua::Host* const host = active_host();

    ScriptVerdict verdict;
    events::Outcome outcome;
    std::string script_name;
    bool saw_run_script = false;
    if (live() && host != nullptr && !g_poison_run_script.load(std::memory_order_acquire)) {
        // `verdict` is written inside the guarded region, so its value after a
        // fault is indeterminate and the fallback re-states it. The default is
        // "do not block", which is the right answer when our own dispatch just
        // faulted: the game's handler runs as it always would.
        KP_HOOK_GUARD_BEGIN("vm.run_script", g_poison_run_script, verdict = ScriptVerdict{})

        const events::EventContract* ev = find_contract("OnRunScript");
        if (ev != nullptr) {
            script_name = read_exostring(name);
            saw_run_script = true;
            {
                // Into the harness ring, before dispatch: what the engine is
                // about to run, whether or not a script then blocks it.
                const kp::harness::EventField fields[] = {
                    kp::harness::EventField::str("script", script_name),
                    kp::harness::EventField::unsigned_("object", object_id),
                    kp::harness::EventField::integer("has_object", has_object),
                };
                kp::harness::ring().push("OnRunScript", ring_tick(host), fields, 3);
            }
            const std::vector<lua::Value> args = {
                lua::Value::str(script_name),
                lua::Value::object(object_id),
                lua::Value::integer(has_object),
            };
            outcome = host->dispatch(*ev, args);
            verdict = decide(*ev, outcome);
            if (verdict.block)
                dispatch_run_script_done(*host, script_name, object_id, has_object,
                                         false, true, outcome);
        }

        KP_HOOK_GUARD_END
    }

    if (verdict.block) return verdict.engine_result;
    if (orig == nullptr) return 0;   // unpatched: we have nothing to forward to
    const int rc = orig(self, name, object_id, has_object);

    // After the engine script, with the engine's own 0/1. A Lua fault here
    // must not rewrite the return the game already produced.
    if (saw_run_script && live() && host != nullptr &&
        !g_poison_run_script.load(std::memory_order_acquire)) {
        KP_HOOK_GUARD_BEGIN("vm.run_script", g_poison_run_script, {})
        dispatch_run_script_done(*host, script_name, object_id, has_object,
                                 rc == 1, false, outcome);
        KP_HOOK_GUARD_END
    }
    return rc;
}

// -------------------------------------------------------------- MainLoop ----

// Hot-reload stats every script file, so it cannot run on every server frame.
// 64 frames is around a second at the rate the server loop actually turns,
// which is fast enough that a player editing a script does not wait for it.
constexpr std::uint64_t kReloadEvery = 64;

void* KP_SERVER_LOOP_CC main_loop_body(void* self) {
    auto orig = reinterpret_cast<MainLoopFn>(g_orig_main_loop.load(std::memory_order_acquire));

    // The client loop stops turning while K1 loads a fresh module, even after
    // it has already run at the menu. The server loop still runs scripts in
    // that interval. Drain here as well: drain's TLS reentrancy guard makes a
    // nested server/client invocation a no-op, and this boundary was already
    // the fallback for builds with no detoured client loop.
    kp::harness::drain();

    lua::Host* const host = active_host();

    if (live() && host != nullptr && !g_poison_main_loop.load(std::memory_order_acquire)) {
        KP_HOOK_GUARD_BEGIN("app.server_main_loop", g_poison_main_loop, {})

        lua::Host& h = *host;
        const std::uint64_t tick = h.tick();

        if (const events::EventContract* ev = find_contract("OnTick"); ev != nullptr) {
            const std::vector<lua::Value> args = {
                lua::Value::integer(static_cast<std::int64_t>(tick)),
            };
            h.dispatch(*ev, args);
        }
        kp::api::timers::pump(kp::api::timers::now_ms(), tick);
        h.advance_tick();

        if (tick % kReloadEvery == 0) {
            std::vector<std::string> errors;
            const unsigned n = h.reload_changed(&errors);
            for (const std::string& e : errors)
                Runtime::instance().log("hot reload: %s", e.c_str());
            if (n != 0) Runtime::instance().log("hot reload: %u script(s)", n);
        }

        KP_HOOK_GUARD_END
    }

    if (orig == nullptr) return nullptr;
    void* result = orig(self);
    unsigned scale = g_tick_scale.load(std::memory_order_acquire);
    if (scale < 1) scale = 1;
    if (scale > 16) scale = 16;
    for (unsigned i = 1; i < scale; ++i) orig(self);
    return result;
}

// ------------------------------------------------------------- DoConsole ----
//
// A keystroke handler, not a line handler: the engine calls this once per
// character while the console is open.
//
// That forces buffer-and-replay rather than pass-through-and-suppress. To
// swallow a line we have to still be holding it when the Enter arrives, so
// nothing is forwarded while a line is being typed; on Enter the line is either
// consumed by us or replayed to the original character by character.
//
// The cost, stated because it will be visible: the game's own echo is deferred
// until Enter, so a player types the line blind. Whether the engine echoes from
// here at all needs confirming against a running game.

// Console input is single-threaded -- it is the game's input thread and there
// is exactly one console. No atomics, because adding them would suggest a
// concurrency that does not exist.
char        g_line[512];
std::size_t g_line_len = 0;

lua_State* g_console_L = nullptr;

int console_print(lua_State* L) {
    std::string out;
    const int n = lua_gettop(L);
    for (int i = 1; i <= n; ++i) {
        if (i > 1) out += "\t";
        const char* s = lua_tostring(L, i);
        out += (s != nullptr) ? s : luaL_typename(L, i);
    }
    Runtime::instance().log("lua: %s", out.c_str());
    return 0;
}

// A state of our own, so `lua exec` works with no script loaded. Sharing a
// script's state instead would let a console typo quarantine that script.
lua_State* console_state() {
    if (g_console_L != nullptr) return g_console_L;
    g_console_L = luaL_newstate();
    if (g_console_L == nullptr) return nullptr;
    luaL_openlibs(g_console_L);
    // The same API every script gets. Without this the console can evaluate Lua
    // and not reach the game, so `lua exec nwscript.call('GetFirstPC')` -- the obvious
    // first thing anyone types -- would answer "attempt to index a nil value".
    init_lua_state(g_console_L);
    // Tag native output from this console state. Lua's print stays unchanged.
    api::push_kp_table(g_console_L);
    lua_pushcfunction(g_console_L, console_print);
    lua_setfield(g_console_L, -2, "print");
    lua_pop(g_console_L, 1);
    return g_console_L;
}

void console_exec(const std::string& code) {
    lua_State* L = console_state();
    if (L == nullptr) { Runtime::instance().log("lua exec: no lua state"); return; }

    const int base = lua_gettop(L);
    // Try the text as an expression first so `lua exec 1+1` answers 2 rather
    // than failing to parse. Falling back to a statement keeps `lua exec x = 1`
    // working too.
    const std::string as_expr = "return " + code;
    if (luaL_loadbuffer(L, as_expr.c_str(), as_expr.size(), "=console") != 0) {
        lua_pop(L, 1);
        if (luaL_loadbuffer(L, code.c_str(), code.size(), "=console") != 0) {
            const char* msg = lua_tostring(L, -1);
            Runtime::instance().log("lua exec: %s", msg != nullptr ? msg : "(parse failed)");
            lua_settop(L, base);
            return;
        }
    }

    if (lua_pcall(L, 0, LUA_MULTRET, 0) != 0) {
        const char* msg = lua_tostring(L, -1);
        Runtime::instance().log("lua exec: %s", msg != nullptr ? msg : "(error)");
        lua_settop(L, base);
        return;
    }

    const int nres = lua_gettop(L) - base;
    if (nres <= 0) { Runtime::instance().log("lua exec: ok"); return; }
    for (int i = 1; i <= nres; ++i) {
        const char* s = lua_tostring(L, base + i);
        Runtime::instance().log("lua exec: %s", s != nullptr ? s : luaL_typename(L, base + i));
    }
    lua_settop(L, base);
}

struct PoisonSite { const char* name; std::atomic<bool>* flag; };

// Every poisonable site, for `lua status` / `lua reload` to report against.
// Event/save/load used to be invisible here -- an operator could not tell
// those sites had gone dark, only that run_script/main_loop/do_console
// hadn't.
const PoisonSite kPoisonSites[] = {
    {"run_script", &g_poison_run_script},
    {"main_loop", &g_poison_main_loop},
    {"do_console", &g_poison_do_console},
    {"event.creature", &g_poison_event_creature},
    {"event.door", &g_poison_event_door},
    {"event.placeable", &g_poison_event_placeable},
    {"event.trigger", &g_poison_event_trigger},
    {"event.module", &g_poison_event_module},
    {"event.area", &g_poison_event_area},
    {"event.encounter", &g_poison_event_encounter},
    {"event.aoe", &g_poison_event_aoe},
    {"event.store", &g_poison_event_store},
    {"event.waypoint", &g_poison_event_waypoint},
    {"save", &g_poison_save},
    {"load", &g_poison_load},
    // The harness drain's own flag: a fault while parsing a request or
    // serialising a reply poisons the harness and nothing else.
    {"harness", &kp::harness::poison_flag()},
    {"creature.ai_action_move_to_point", &g_poison_move_to_point},
    {"creature.add_move_to_point_action", &g_poison_add_move_to_point},
};

std::string poisoned_site_list() {
    std::string list;
    for (const PoisonSite& p : kPoisonSites) {
        if (!p.flag->load(std::memory_order_acquire)) continue;
        if (!list.empty()) list += ", ";
        list += p.name;
    }
    return list;
}

void console_status() {
    Runtime& rt = Runtime::instance();
    rt.log("status: KotorPhasor %s", KP_VERSION);
    rt.log("status: phase=%s build=%s live=%s", to_string(rt.phase()),
           rt.build().empty() ? "(none)" : rt.build().c_str(), live() ? "yes" : "no");
    if (!rt.failure().empty()) rt.log("status: failure=%s", rt.failure().c_str());

    if (hooks::HookSet* hs = rt.hooks(); hs != nullptr)
        rt.log("status: %zu hook(s) installed", hs->installed_count());

    const std::string poisoned = poisoned_site_list();
    if (poisoned.empty()) rt.log("status: no site poisoned");
    else                  rt.log("status: poisoned: %s", poisoned.c_str());

    // Point at the way out, rather than leaving the player to read "live=no"
    // and conclude the mod is broken.
    if (!live() && rt.phase() == Phase::Running)
        rt.log("status: scripting is off after a fault; `lua reload` turns it back on");

    lua::Host* h = active_host();
    if (h == nullptr) { rt.log("status: no lua host"); return; }
    rt.log("status: tick=%llu, %zu script(s)", static_cast<unsigned long long>(h->tick()),
           h->scripts().size());
    for (const auto& s : h->scripts()) {
        const char* st = "?";
        switch (s->state()) {
        case lua::ScriptState::Loaded:       st = "loaded"; break;
        case lua::ScriptState::FailedToLoad: st = "failed"; break;
        case lua::ScriptState::Quarantined:  st = "quarantined"; break;
        case lua::ScriptState::Unloaded:     st = "unloaded"; break;
        }
        rt.log("status:   %s priority=%d state=%s errors=%u", s->name().c_str(), s->priority(),
               st, s->error_count());
    }
}

void console_reload() {
    lua::Host* h = active_host();
    if (h == nullptr) { Runtime::instance().log("lua reload: no lua host"); return; }
    std::vector<std::string> errors;
    const unsigned loaded = h->load_all(errors);
    for (const std::string& e : errors) Runtime::instance().log("lua reload: %s", e.c_str());
    Runtime::instance().log("lua reload: %u script(s) loaded", loaded);

    // The one command that can bring scripting back after a fault.
    //
    // A fault takes the whole runtime out of service, because the longjmp that
    // recovered from it can leave a lua_State unwound part-way through a
    // pcall. Reloading builds every state from scratch, which is exactly the
    // thing that was suspect -- so re-arming here is sound, and without it this
    // command would report "N scripts loaded" while nothing ever fires again.
    if (!live()) {
        set_live(true);
        Runtime::instance().log("lua reload: scripting re-armed after a fault");
    }

    // Poison is per site and it stays. That body faulted in native code, and a
    // fresh set of Lua states does not make running it again safe. Said out
    // loud, because "reloaded but this event still will not fire" is exactly
    // the kind of half-recovery that wastes an evening.
    const std::string poisoned = poisoned_site_list();
    if (!poisoned.empty()) {
        Runtime::instance().log("lua reload: still poisoned (%s); those events stay silent "
                                "until the game restarts", poisoned.c_str());
    }
}

// Returns true when the line was consumed and must not reach the game.
bool handle_line(const std::string& line) {
    // Built-ins first, and unconditionally: they have to work when no script is
    // loaded, when the Lua host failed to start, and when a site is poisoned.
    // That is the whole point of having them.
    if (line.rfind("lua", 0) == 0 && (line.size() == 3 || line[3] == ' ')) {
        const std::string rest = line.size() > 3 ? line.substr(4) : std::string();
        std::size_t begin = rest.find_first_not_of(' ');
        const std::string args = begin == std::string::npos ? std::string() : rest.substr(begin);

        if (args == "reload")                 console_reload();
        else if (args == "status")            console_status();
        else if (args.rfind("exec ", 0) == 0) console_exec(args.substr(5));
        else Runtime::instance().log("lua: commands are `lua reload`, `lua status`, "
                                     "`lua exec <code>`");
        return true;
    }

    lua::Host* h = active_host();
    if (!live() || h == nullptr) return false;

    const events::EventContract* ev = find_contract("OnConsoleCommand");
    if (ev == nullptr) return false;   // no contract, so no script can claim it

    const std::vector<lua::Value> args = {lua::Value::str(line)};
    const events::Outcome outcome = h->dispatch(*ev, args);
    return outcome.claimed && !outcome.bool_result;   // false means swallow
}

void replay(DoConsoleFn orig, const char* text, std::size_t len, char terminator) {
    if (orig == nullptr) return;
    for (std::size_t i = 0; i < len; ++i) orig(text[i]);
    orig(terminator);
}

void __attribute__((cdecl)) do_console_body(char c) {
    auto orig = reinterpret_cast<DoConsoleFn>(g_orig_do_console.load(std::memory_order_acquire));

    if (g_poison_do_console.load(std::memory_order_acquire)) {
        if (orig != nullptr) orig(c);
        return;
    }

    // Backspace edits our buffer instead of the game's. The game's buffer is
    // empty until Enter, so forwarding a backspace would delete nothing there
    // and desynchronise the two.
    if (c == '\b' || c == 0x7f) {
        if (g_line_len > 0) --g_line_len;
        return;
    }

    if (c != '\r' && c != '\n') {
        // Anything that is not text is the game's to interpret -- escape,
        // arrow-key encodings, whatever else the console reads. Buffering those
        // would break editing we do not implement.
        const auto uc = static_cast<unsigned char>(c);
        if (uc < 0x20) { if (orig != nullptr) orig(c); return; }

        if (g_line_len < sizeof g_line) {
            g_line[g_line_len++] = c;
        } else {
            // Longer than we will hold. Give the line back to the game rather
            // than silently truncating what the player typed.
            replay(orig, g_line, g_line_len, c);
            g_line_len = 0;
        }
        return;
    }

    const std::size_t len = g_line_len;
    g_line_len = 0;   // reset before anything can fail

    bool consumed = false;
    {
        const std::string line(g_line, len);
        KP_HOOK_GUARD_BEGIN("console.do_console", g_poison_do_console, consumed = false)
        consumed = handle_line(line);
        KP_HOOK_GUARD_END
    }

    if (!consumed) replay(orig, g_line, len, c);
}

// ---------------------------------------------------------- EventHandler ----
//
// All ten object types share this signature. Five stack arguments after `this`,
// callee-cleans: the compiler must emit `ret $0x14`. A shorter parameter list
// skews ESP on that thread permanently.
//
// pEventData is NOT always a CScriptEvent. Lookup keys on (site, outer id)
// and, when outer id is SIGNAL_EVENT, the script event type. Named slots that
// only ever reach RunScript are not looked up here.

using EventHandlerFn = void (KP_THISCALL*)(void*, unsigned long, unsigned long,
                                           void*, unsigned long, unsigned long);

void persist_situation(const std::string& blob) {
    g_situation_blob = blob;
    events::write_situation_blob(g_situation_path, blob);
}

std::string load_situation() {
    if (!g_situation_path.empty()) {
        const std::string blob = events::read_situation_blob(g_situation_path);
        if (!blob.empty() || g_situation_blob.empty())
            g_situation_blob = blob;
    }
    return g_situation_blob;
}

void event_handler_common(void* self, unsigned long n_event_id,
                          unsigned long n_caller, void* payload,
                          unsigned long day, unsigned long time,
                          const char* site, std::atomic<void*>& orig_slot,
                          std::atomic<bool>& poison) {
    auto orig = reinterpret_cast<EventHandlerFn>(
        orig_slot.load(std::memory_order_acquire));

    lua::Host* const host = active_host();
    bool skip = false;
    if (live() && host != nullptr && !poison.load(std::memory_order_acquire)) {
        KP_HOOK_GUARD_BEGIN(site, poison, skip = false)

        int script_type = -1;
        if (events::payload_is_script_event(static_cast<int>(n_event_id))) {
            events::ScriptEventView view{payload};
            script_type = events::script_event_type(view);
        }
        const events::EventContract* ev = events::find_by_site(
            site, static_cast<int>(n_event_id), script_type);
        if (ev != nullptr) {
            {
                // The ring record carries the contract's own name, which is
                // a static string from the generated table.
                const kp::harness::EventField fields[] = {
                    kp::harness::EventField::unsigned_(
                        "object", events::object_id_from_handler(self, site)),
                    kp::harness::EventField::unsigned_("caller", n_caller),
                    kp::harness::EventField::integer("event_id",
                                                     static_cast<std::int64_t>(n_event_id)),
                    kp::harness::EventField::integer("type", script_type),
                };
                kp::harness::ring().push(ev->lua_name.c_str(), ring_tick(host), fields, 4);
            }
            events::HandlerFrame frame;
            frame.self = self;
            frame.caller = static_cast<std::uint32_t>(n_caller);
            frame.payload = payload;
            frame.calendar_day = static_cast<std::uint32_t>(day);
            frame.time_of_day = static_cast<std::uint32_t>(time);
            frame.hook_site = site;
            frame.outer_event_id = static_cast<int>(n_event_id);
            const events::Outcome outcome =
                host->dispatch(*ev, events::shape_handler_args(*ev, frame));
            if (ev->blocking)
                skip = events::blocking_verdict(*ev, outcome).skip_original;
        }

        KP_HOOK_GUARD_END
    }

    if (skip) return;
    if (orig == nullptr) return;
    orig(self, n_event_id, n_caller, payload, day, time);
}

void KP_THISCALL creature_event_body(void* self, unsigned long id, unsigned long caller,
                                     void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.creature", g_orig_creature,
                         g_poison_event_creature);
}
void KP_THISCALL door_event_body(void* self, unsigned long id, unsigned long caller,
                                 void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.door", g_orig_door,
                         g_poison_event_door);
}
void KP_THISCALL placeable_event_body(void* self, unsigned long id, unsigned long caller,
                                      void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.placeable", g_orig_placeable,
                         g_poison_event_placeable);
}
void KP_THISCALL trigger_event_body(void* self, unsigned long id, unsigned long caller,
                                    void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.trigger", g_orig_trigger,
                         g_poison_event_trigger);
}
void KP_THISCALL module_event_body(void* self, unsigned long id, unsigned long caller,
                                   void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.module", g_orig_module,
                         g_poison_event_module);
}
void KP_THISCALL area_event_body(void* self, unsigned long id, unsigned long caller,
                                 void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.area", g_orig_area,
                         g_poison_event_area);
}
void KP_THISCALL encounter_event_body(void* self, unsigned long id, unsigned long caller,
                                      void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.encounter", g_orig_encounter,
                         g_poison_event_encounter);
}
void KP_THISCALL aoe_event_body(void* self, unsigned long id, unsigned long caller,
                                void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.aoe", g_orig_aoe,
                         g_poison_event_aoe);
}
void KP_THISCALL store_event_body(void* self, unsigned long id, unsigned long caller,
                                  void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.store", g_orig_store,
                         g_poison_event_store);
}
void KP_THISCALL waypoint_event_body(void* self, unsigned long id, unsigned long caller,
                                     void* data, unsigned long day, unsigned long time) {
    event_handler_common(self, id, caller, data, day, time, "event.waypoint", g_orig_waypoint,
                         g_poison_event_waypoint);
}

// Save and load both take three stack arguments.  In K1,
// CVirtualMachine::SaveScriptSituation at 0x5D47A0 reads its situation/GFF/
// struct arguments and returns `ret 0xC`: the first WriteFieldINT receives
// the GFF as `this`.  A one-argument detour shifted the latter two arguments,
// handing WriteFieldINT 0xC as its `this` during module-transition saves and
// faulting at CResGFF+0x98 (0x004127C5).  Load's three-argument ABI was
// already established from its callers and epilogue; preserve all arguments
// for both hooks.
using SaveSituationFn = int (KP_THISCALL*)(void*, void*, void*, void*);
using LoadSituationFn = int (KP_THISCALL*)(void*, void*, void*, void*);

int KP_THISCALL save_situation_body(void* self, void* situation, void* gff, void* structure) {
    auto orig = reinterpret_cast<SaveSituationFn>(g_orig_save.load(std::memory_order_acquire));
    lua::Host* const host = active_host();
    if (live() && host != nullptr && !g_poison_save.load(std::memory_order_acquire)) {
        KP_HOOK_GUARD_BEGIN("vm.save_script_situation", g_poison_save, {})
        kp::harness::ring().push("OnSave", ring_tick(host));
        if (const events::EventContract* ev = find_contract("OnSave")) {
            const events::Outcome outcome = host->dispatch(*ev, {});
            if (outcome.claimed) persist_situation(outcome.string_result);
        }
        KP_HOOK_GUARD_END
    }
    if (orig == nullptr) return 0;
    return orig(self, situation, gff, structure);
}

int KP_THISCALL load_situation_body(void* self, void* a, void* b, void* c) {
    auto orig = reinterpret_cast<LoadSituationFn>(g_orig_load.load(std::memory_order_acquire));
    lua::Host* const host = active_host();
    if (live() && host != nullptr && !g_poison_load.load(std::memory_order_acquire)) {
        KP_HOOK_GUARD_BEGIN("vm.load_script_situation", g_poison_load, {})
        kp::harness::ring().push("OnLoad", ring_tick(host));
        if (const events::EventContract* ev = find_contract("OnLoad")) {
            const std::vector<lua::Value> args = {
                lua::Value::str(load_situation()),
            };
            host->dispatch(*ev, args);
        }
        KP_HOOK_GUARD_END
    }
    if (orig == nullptr) return 0;
    return orig(self, a, b, c);
}

// ------------------------------------------------ movement admission trace --
//
// This is deliberately a trace of the entry gate, rather than a movement
// command or a retry policy.  The original routine owns all state changes.
// Earlier K1 predicates remain the engine's concern. This trace observes only
// the suppression pair at creature+0x1f8/+0xa8c and path context at +0x340.
namespace {
bool trace_u32(const void* base, std::size_t offset, std::uint32_t& out) {
    if (base == nullptr) return false;
    const std::uintptr_t p = reinterpret_cast<std::uintptr_t>(base);
    if (offset > static_cast<std::size_t>(~std::uintptr_t(0) - p)) return false;
    const std::uintptr_t at = p + offset;
    if (!platform::is_readable(reinterpret_cast<const void*>(at), sizeof out)) return false;
    std::memcpy(&out, reinterpret_cast<const void*>(at), sizeof out);
    return true;
}

}  // namespace

int KP_THISCALL creature_move_to_point_body(void* creature, void* action_node) {
    auto orig = reinterpret_cast<MoveToPointFn>(
        g_orig_move_to_point.load(std::memory_order_acquire));
    lua::Host* const host = active_host();

    if (live() && host != nullptr && !g_poison_move_to_point.load(std::memory_order_acquire)) {
        KP_HOOK_GUARD_BEGIN("creature.ai_action_move_to_point", g_poison_move_to_point, {})
        std::uint32_t creature_id = 0, action = 0, suppressed = 0, raw_mode = 0, path_context = 0;
        const bool readable = trace_u32(creature, 4, creature_id) &&
                              trace_u32(action_node, 0x6c, action) &&
                              trace_u32(creature, 0x1f8, suppressed) &&
                              trace_u32(creature, 0xa8c, raw_mode) &&
                              trace_u32(creature, 0x340, path_context);
        const char* gate = "partial_unreadable";
        if (readable && suppressed != 0 && static_cast<std::int32_t>(raw_mode) != 0 &&
            raw_mode != 4 && raw_mode != 5 && raw_mode != 6)
            gate = "suppressed_1f8";
        else if (readable && path_context == 0)
            gate = "missing_path_context";
        else if (readable)
            gate = "prepath_unclassified";
        const kp::harness::EventField fields[] = {
            kp::harness::EventField::unsigned_("creature", creature_id),
            kp::harness::EventField::unsigned_("action", action),
            kp::harness::EventField::str("gate", gate),
            kp::harness::EventField::integer("a8c", static_cast<std::int32_t>(raw_mode)),
        };
        kp::harness::ring().push("move_admission", ring_tick(host), fields, 4);
        KP_HOOK_GUARD_END
    }
    return orig != nullptr ? orig(creature, action_node) : 0;
}

// ---------------------------------------------------------- client loop -----
//
// WinMain calls this every idle iteration, with or without a server, so it
// is the one per-frame site that runs on the main menu. That makes it the
// harness's drain point: requests are taken off the channel and executed
// here, on the main thread, before the engine's frame.
//
// No guard is armed in this body. The drain arms its own around parse and
// serialise, and runs engine calls unarmed on purpose (see harness/
// commands.hpp); after_frame() re-applies the harness time scale and takes a
// pending screenshot once the frame has rendered, both engine work.
//
// The return value is the engine's exit flag, which WinMain ORs into its
// own. Returning 1 here is what `quit` does: a clean exit through the
// engine's shutdown, with the reply already handed to the socket.
int KP_CLIENT_LOOP_CC client_main_loop_body(void* self) {
    auto orig = reinterpret_cast<ClientLoopFn>(g_orig_client_loop.load(std::memory_order_acquire));

    if (orig == nullptr) return 0;
    const int result = orig(self);

    const auto frame = g_client_loop_frames.fetch_add(1, std::memory_order_relaxed) + 1;
    if ((frame % 100) == 0)
        Runtime::instance().log("client loop cave: %llu frames", static_cast<unsigned long long>(frame));
    kp::harness::note_client_frame();
    kp::harness::drain();

    kp::harness::after_frame();

    if (kp::harness::quit_requested()) {
        // Give the listener a moment to write the `quit` reply. Bounded: a
        // client that stopped reading must not keep the process alive.
        kp::harness::stop_after_flush();
        return 1;
    }
    return result;
}

// K2-native reaches MainLoop through a render/update wrapper on some launch
// paths. Keep a second, independently resolved drain point for that path.
int __attribute__((cdecl)) client_frame_wrapper_body(void* self) {
    auto orig = reinterpret_cast<ClientFrameWrapperFn>(g_orig_client_frame_wrapper.load(std::memory_order_acquire));
    static std::atomic<unsigned> wrapper_frames{0};
    const unsigned entered = wrapper_frames.fetch_add(1, std::memory_order_relaxed) + 1;
    if ((entered % 100) == 0)
        Runtime::instance().log("client frame wrapper: %u entries", entered);
    const int result = orig != nullptr ? orig(self) : 0;
    kp::harness::note_client_frame();
    kp::harness::drain();
    kp::harness::after_frame();
    return result;
}

}  // namespace

// ------------------------------------------------------------- wiring in ----

void set_situation_path(std::string path) { g_situation_path = std::move(path); }

// The poison table as a list, for the harness `status` and `state` replies.
// Same source as `lua status`, so the two never disagree about what is dark.
std::vector<std::string> poisoned_sites() {
    std::vector<std::string> out;
    for (const PoisonSite& p : kPoisonSites)
        if (p.flag->load(std::memory_order_acquire)) out.emplace_back(p.name);
    return out;
}

void set_tick_scale(unsigned n) {
    if (n < 1) n = 1;
    if (n > 16) n = 16;
    g_tick_scale.store(n, std::memory_order_release);
}

unsigned tick_scale() { return g_tick_scale.load(std::memory_order_acquire); }

namespace {
int l_speed(lua_State* L) {
    if (lua_gettop(L) >= 1) set_tick_scale(static_cast<unsigned>(luaL_checkinteger(L, 1)));
    lua_pushinteger(L, static_cast<lua_Integer>(tick_scale()));
    return 1;
}
}  // namespace

void register_director(lua_State* L) {
    lua_getglobal(L, "kp");
    if (!lua_istable(L, -1)) {
        lua_pop(L, 1);
        lua_newtable(L);
        lua_pushvalue(L, -1);
        lua_setglobal(L, "kp");
    }
    lua_pushcfunction(L, l_speed);
    lua_setfield(L, -2, "speed");
    lua_pop(L, 1);
}

void* run_script_detour() { return reinterpret_cast<void*>(&run_script_body); }
void* main_loop_detour()  { return reinterpret_cast<void*>(&main_loop_body); }
void* do_console_detour() { return reinterpret_cast<void*>(&do_console_body); }
void* creature_event_detour()  { return reinterpret_cast<void*>(&creature_event_body); }
void* door_event_detour()      { return reinterpret_cast<void*>(&door_event_body); }
void* placeable_event_detour() { return reinterpret_cast<void*>(&placeable_event_body); }
void* trigger_event_detour()   { return reinterpret_cast<void*>(&trigger_event_body); }
void* module_event_detour()    { return reinterpret_cast<void*>(&module_event_body); }
void* area_event_detour()      { return reinterpret_cast<void*>(&area_event_body); }
void* encounter_event_detour() { return reinterpret_cast<void*>(&encounter_event_body); }
void* aoe_event_detour()       { return reinterpret_cast<void*>(&aoe_event_body); }
void* store_event_detour()     { return reinterpret_cast<void*>(&store_event_body); }
void* waypoint_event_detour()  { return reinterpret_cast<void*>(&waypoint_event_body); }
void* save_situation_detour()  { return reinterpret_cast<void*>(&save_situation_body); }
void* load_situation_detour()  { return reinterpret_cast<void*>(&load_situation_body); }
void* creature_move_to_point_detour() { return reinterpret_cast<void*>(&creature_move_to_point_body); }
void* add_move_to_point_detour() { return reinterpret_cast<void*>(&add_move_to_point_body); }
void* net_start_connect_detour() { return reinterpret_cast<void*>(&net_start_connect_body); }
void* net_start_server_mode_detour() { return reinterpret_cast<void*>(&net_start_server_mode_body); }
void* net_send_message_detour() { return reinterpret_cast<void*>(&net_send_message_body); }
void* net_process_frames_detour() { return reinterpret_cast<void*>(&net_process_frames_body); }
void* client_area_get_server_area_detour() {
    return reinterpret_cast<void*>(&client_area_get_server_area_body);
}
void set_net_destination_offset(std::uint32_t offset) {
    g_net_destination_offset.store(offset, std::memory_order_release);
}
void* client_main_loop_detour() { return reinterpret_cast<void*>(&client_main_loop_body); }
void* client_frame_wrapper_detour() { return reinterpret_cast<void*>(&client_frame_wrapper_body); }

void bind_originals(hooks::HookSet& set) {
    g_orig_run_script.store(set.original("vm.run_script"), std::memory_order_release);
    g_orig_main_loop.store(set.original("app.server_main_loop"), std::memory_order_release);
    g_orig_do_console.store(set.original("console.do_console"), std::memory_order_release);
    g_orig_creature.store(set.original("event.creature"), std::memory_order_release);
    g_orig_door.store(set.original("event.door"), std::memory_order_release);
    g_orig_placeable.store(set.original("event.placeable"), std::memory_order_release);
    g_orig_trigger.store(set.original("event.trigger"), std::memory_order_release);
    g_orig_module.store(set.original("event.module"), std::memory_order_release);
    g_orig_area.store(set.original("event.area"), std::memory_order_release);
    g_orig_encounter.store(set.original("event.encounter"), std::memory_order_release);
    g_orig_aoe.store(set.original("event.aoe"), std::memory_order_release);
    g_orig_store.store(set.original("event.store"), std::memory_order_release);
    g_orig_waypoint.store(set.original("event.waypoint"), std::memory_order_release);
    g_orig_save.store(set.original("vm.save_script_situation"), std::memory_order_release);
    g_orig_load.store(set.original("vm.load_script_situation"), std::memory_order_release);
    g_orig_move_to_point.store(set.original("creature.ai_action_move_to_point"), std::memory_order_release);
    g_orig_add_move_to_point.store(set.original("creature.add_move_to_point_action"),
                                   std::memory_order_release);
    g_orig_client_loop.store(set.original("app.client_main_loop"), std::memory_order_release);
    g_orig_client_frame_wrapper.store(set.original("app.client_frame_wrapper"), std::memory_order_release);
    g_orig_net_start_connect.store(set.original("net.start_connect_to_session"), std::memory_order_release);
    g_orig_net_start_server.store(set.original("net.start_server_mode"), std::memory_order_release);
    g_orig_net_send.store(set.original("net.send_message_to_player"), std::memory_order_release);
    g_orig_net_process.store(set.original("net.process_received_frames"), std::memory_order_release);
    g_orig_client_area_get_server_area.store(
        set.original("client.area_get_server_area"), std::memory_order_release);
    // The adapter's own detours (game speed, movies) keep their originals on
    // its side of the interface.
    kp::harness::bind_adapter_originals(set);
}

void clear_originals() {
    // Uninstalling unmaps the trampolines, so these have to be dropped before
    // the uninstall and not after. A body holding a stale pointer would fault
    // on a page that is no longer there.
    g_orig_run_script.store(nullptr, std::memory_order_release);
    g_orig_main_loop.store(nullptr, std::memory_order_release);
    g_orig_do_console.store(nullptr, std::memory_order_release);
    g_orig_creature.store(nullptr, std::memory_order_release);
    g_orig_door.store(nullptr, std::memory_order_release);
    g_orig_placeable.store(nullptr, std::memory_order_release);
    g_orig_trigger.store(nullptr, std::memory_order_release);
    g_orig_module.store(nullptr, std::memory_order_release);
    g_orig_area.store(nullptr, std::memory_order_release);
    g_orig_encounter.store(nullptr, std::memory_order_release);
    g_orig_aoe.store(nullptr, std::memory_order_release);
    g_orig_store.store(nullptr, std::memory_order_release);
    g_orig_waypoint.store(nullptr, std::memory_order_release);
    g_orig_save.store(nullptr, std::memory_order_release);
    g_orig_load.store(nullptr, std::memory_order_release);
    g_orig_move_to_point.store(nullptr, std::memory_order_release);
    g_orig_add_move_to_point.store(nullptr, std::memory_order_release);
    g_orig_client_loop.store(nullptr, std::memory_order_release);
    g_orig_client_frame_wrapper.store(nullptr, std::memory_order_release);
    g_orig_net_start_connect.store(nullptr, std::memory_order_release);
    g_orig_net_start_server.store(nullptr, std::memory_order_release);
    g_orig_net_send.store(nullptr, std::memory_order_release);
    g_orig_net_process.store(nullptr, std::memory_order_release);
    g_orig_client_area_get_server_area.store(nullptr, std::memory_order_release);
    g_net_destination_offset.store(0, std::memory_order_release);
    g_server_net.store(nullptr, std::memory_order_release);
    g_client_net.store(nullptr, std::memory_order_release);
    g_client_support_server_net.store(nullptr, std::memory_order_release);

    if (g_console_L != nullptr) { lua_close(g_console_L); g_console_L = nullptr; }
}

}  // namespace kp::runtime
