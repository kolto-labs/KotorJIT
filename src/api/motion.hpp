#pragma once
// kp.motion: server placeable capture (M1) plus relocate / restore / observe
// (M2), K1 GOG only.
// Engine calls: the typed server lookup
// CServerExoApp::GetPlaceableByGameObjectID (0x4AE7A0) and, for writes only,
// CSWSObject::SetPosition (0x4CD1A0) with flags (1,1,0). Every other value is a
// plain memory read through a fallible reader. Orientation is never written.
// Evidence: /home/brunner56/kp-live-20260922/motion-m0-rederivation.md and
// motion-m0-verification.md (verdict CONFIRMS); only its "safe" list is used.
// Plan: /home/brunner56/kp-live-20260922/motion-m2-plan.md.
//
// Every public operation asks api/engine_gate.hpp FIRST. A gate refusal does
// zero memory reads and zero engine calls.
#include "api/model.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <map>
#include <string>

struct lua_State;
namespace kp::api::motion {
using Address = std::uint64_t;
using model::Abi;
// Exact byte guard: an instruction or literal whose bytes pin an offset,
// global, constant or vtable. Hex is lowercase, even length, 1..16 bytes.
struct Span { Address va; const char* hex; };
constexpr std::size_t max_span_bytes = 16;
// A vtable slot that must hold the given function VA.
struct Slot { Address va; Address target; };
struct Profile {
    const char* name; const char* sha256; Abi abi; unsigned width; Address preferred_base;
    Address manager_slot;       // g_pAppManager
    unsigned manager_server;    // CAppManager -> CServerExoApp*
    unsigned server_internal;   // CServerExoApp -> CServerExoAppInternal*
    unsigned internal_array;    // CServerExoAppInternal -> server object array
    Address get_placeable;      // CServerExoApp::GetPlaceableByGameObjectID
    Address set_position;       // CSWSObject::SetPosition: thiscall(this, const Vector*, a2, a3, a4), ret 0x10
    Address placeable_vtable;   // CSWSPlaceable vtable
    std::uint8_t placeable_type;// CGameObject type byte for a placeable
    unsigned id, type;          // CGameObject
    unsigned area_id, position, orientation;         // CSWSObject
    unsigned push_gate, dirty;                       // CSWSObject
    unsigned aabb_marker, quaternion;                // CSWSPlaceable
    std::array<Span, 32> spans; // unused tail entries have va 0
    std::array<Slot, 4> slots;
};
const std::array<Profile, 1>& profiles();
const Profile* profile_for(const std::string& sha);

// Closed set of failure kinds. Identity covers "not a placeable": null lookup,
// wrong type byte, wrong vtable or an id that does not round-trip.
// M2 adds: Stale (capture no longer matches the object), Collision (walkmesh
// registered, no opt-in), Bounds (policy distances), Owned (another script
// owns the object), NotOwner (restore by a non-owner), Conflict (restore found
// the object moved by someone else; ownership released, no write), Mutation
// (the setter ran but the readback disagrees; the write may have happened).
enum class Failure { None, Unsupported, Guard, Chain, Identity, Value,
                     Stale, Collision, Bounds, Owned, NotOwner, Conflict, Mutation };
constexpr Failure all_failures[] = {Failure::Unsupported, Failure::Guard, Failure::Chain, Failure::Identity,
    Failure::Value, Failure::Stale, Failure::Collision, Failure::Bounds, Failure::Owned, Failure::NotOwner,
    Failure::Conflict, Failure::Mutation};
const char* failure_name(Failure);

struct Backend {
    virtual ~Backend() = default;
    virtual Abi abi() const = 0;
    virtual unsigned width() const = 0;
    virtual bool read(Address, void*, std::size_t) const = 0;
    // thiscall(CServerExoApp*, uint32 id) -> CSWSPlaceable* or 0.
    virtual Address placeable(Address function, Address server, std::uint32_t id) = 0;
    // thiscall CSWSObject::SetPosition(object, &pos, a2, a3, a4), ret 0x10.
    // The only engine write. pos is 3 floats, copied by the engine.
    virtual void set_position(Address function, Address object, const std::array<float, 3>& pos,
                              std::int32_t a2, std::int32_t a3, std::int32_t a4) = 0;
};
constexpr std::uint32_t dirty_position_bit = 2;    // SetPosition a4==0: |= 2
constexpr std::uint32_t dirty_orientation_bit = 4; // SetOrientation: |= 4
struct Capture {
    std::uint64_t epoch = 0;
    std::uint32_t id = 0;
    Address object = 0;
    std::uint32_t area_id = 0;
    std::array<float, 3> position{};
    std::array<float, 3> orientation{};
    float facing = 0;                  // atan2(orientation.y, orientation.x) in degrees, [0,360)
    std::uint32_t push_gate_raw = 0;   // +0x1F8, a client-push gate; meaning of the value unverified
    bool dirty_position = false;       // +0x1FC & 2
    bool dirty_orientation = false;    // +0x1FC & 4
    bool collision_registered = false; // +0x344 >= 0
    std::array<float, 4> quaternion_raw{}; // +0x428, component order unverified
    bool owned = false;                // M2: the calling state owns this object in the ledger
};

// M2 write policy (plan section 4). Distances in metres; policy, not evidence.
constexpr double max_step = 5.0;       // |target - current|
constexpr double max_dz = 1.0;         // |target.z - current.z|
constexpr double max_from_origin = 25.0; // |target - origin|
constexpr double max_coord = 1e5;      // |component|
// Who is asking to write. The Lua layer asks the injected owner probe; the
// runtime maps Script::owner(L) to None (console, harness, bare state),
// Staged (owner->staged(): a chunk top level, or the old generation while its
// successor is staged) or Loaded.
enum class Writer { None, Staged, Loaded };
enum class Status { Moved, Noop };
struct Observation {
    bool pushed = false;               // dirty position bit clear and push gate != 0
    std::uint32_t push_gate_raw = 0;
    bool dirty_position = false;
    bool has_write = false;            // the ledger has an entry for this id
    bool has_tick = false;             // a tick source is bound and the entry has a write tick
    std::uint64_t ticks_since_write = 0;
};
// One ledger entry per moved object id. Keyed on the per-state owner token,
// never on lua_State* (pointers are reused after lua_close). object is compared,
// never dereferenced.
struct Entry {
    std::uint64_t owner_token = 0;
    std::uint64_t binding_epoch = 0;
    Address object = 0;
    std::uint32_t area_id = 0;
    std::array<float, 3> origin_position{};
    std::array<float, 3> origin_orientation{};
    std::array<float, 3> last_written{};
    std::uint64_t writes = 0;
    bool has_tick = false;
    std::uint64_t last_write_tick = 0;
};
// Float equality exactly as the engine's 0x4AA980 (fcomp on each of the 3
// floats): equal bits, or both zero of either sign. NaN is refused earlier.
bool engine_equal(const std::array<float, 3>&, const std::array<float, 3>&);
// Bit-for-bit equality (the stale, readback and restore fences).
bool bit_equal(const std::array<float, 3>&, const std::array<float, 3>&);
class Operations {
public:
    bool bind(const std::string& verified_sha, Address loaded_base, Backend*, std::string& error);
    void unbind();
    bool available() const { return backend_ != nullptr; }
    const Profile* profile() const { return profile_; }
    std::uint64_t epoch() const { return epoch_; }
    // Fills out only on success; on failure out is left untouched.
    bool capture(std::uint32_t id, Capture& out, std::string& error);
    // M2. token is the calling state's owner token (0 = none). Every call is
    // gated, then checked in plan order R1..R12. out/status are written only
    // on success.
    bool relocate(std::uint64_t token, Writer, const Capture& from, const std::array<float, 3>& target,
                  bool allow_stale_collision, Capture& out, Status& status, std::string& error);
    // Restore is exempt from the Staged half of R3: an owner can always put
    // things back. On success the entry is dropped.
    bool restore(std::uint64_t token, Writer, std::uint32_t id, Capture& out, std::string& error);
    // Server-side proxy only; no client field is read. expected_object is
    // the capture's object pointer (identity fence).
    bool observe(std::uint32_t id, Address expected_object, Observation& out, std::string& error);
    std::uint64_t owner_of(std::uint32_t id) const;   // 0 = unowned
    const Entry* entry(std::uint32_t id) const;
    std::size_t ledger_size() const { return ledger_.size(); }
    Failure last_failure() const { return failure_; }
    static bool valid_span(const Span&);
private:
    bool fail(Failure, std::string& error, const std::string& text);
    bool guards(std::string& error);
    bool pointer(Address, Address&) const;
    // Ungated: guards, chain, getter (the one engine read call), fences,
    // fields. Callers gate first.
    bool locate(std::uint32_t id, Capture& out, std::string& error);
    // Raw reads on a known object pointer, no getter: fences + fields.
    bool read_fields(Address object, std::uint32_t id, Capture& out, std::string& error);
    // One setter call plus readback. On success out holds the readback.
    bool write_and_verify(const Capture& before, const std::array<float, 3>& target, Capture& out,
                          std::string& error);
    Address at(Address va) const { return loaded_base_ + va - profile_->preferred_base; }
    const Profile* profile_ = nullptr;
    Backend* backend_ = nullptr;
    Address loaded_base_ = 0;
    std::uint64_t epoch_ = 0;
    Failure failure_ = Failure::None;
    std::map<std::uint32_t, Entry> ledger_;  // cleared on bind/unbind
};
Operations& operations();
Backend* native_backend(model::Reader, void* context);
bool bind_native(const std::string& verified_sha, Address loaded_base, model::Reader, void*, std::string&);
void register_all(lua_State*);

// --- runtime injection points (bound by the I-M2 integrator) ---------------
// Owner probe: maps a lua_State to Writer. Unbound = Writer::None (fail
// closed: no state may write). Runtime binding:
//   Script* s = lua::Script::owner(L); !s ? None : s->staged() ? Staged : Loaded
using OwnerProbe = Writer (*)(lua_State*, void* context);
void bind_owner_probe(OwnerProbe, void* context);
// Tick source for observe().ticks_since_write. Unbound = no tick fields.
// Runtime binding: active_host()->tick().
using TickSource = std::uint64_t (*)(void* context);
void bind_tick(TickSource, void* context);
bool current_tick(std::uint64_t& out);
// The calling state's owner token, stored by register_all under a private
// registry key. 0 when register_all never ran on this state.
std::uint64_t state_token(lua_State*);

// --- M3 hook point (NOT implemented in M2) ---------------------------------
// M3 adds `void release_state(lua_State*)`: read state_token(L); for every
// ledger entry with that token run restore's fences and, if they pass, one
// SetPosition back to the origin; otherwise log and write nothing; then drop
// the token's entries. Contract:
//   * no Lua calls (every fallible read happens before the single setter);
//   * gated: when engine::on_engine_thread() is false (Runtime::stop, the
//     worker thread) it writes nothing and logs one "not restored" line per
//     entry;
//   * its only caller is L3's ownership::run_and_clear(L), reached from
//     HostConfig::on_state_closing. No direct runtime -> motion call.
// Until M3 lands, an entry whose state closed (unload, hot reload) is an
// orphan: the object stays at the moved pose and stays locked against other
// scripts until the binding is dropped (Runtime stop/rebind clears the
// ledger). capabilities().limits says so.
} // namespace kp::api::motion
