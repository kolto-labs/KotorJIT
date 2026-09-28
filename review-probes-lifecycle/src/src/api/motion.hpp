#pragma once
// kp.motion Stage M1: read-only capture of one server placeable, K1 GOG only.
// The only engine call is the typed server lookup
// CServerExoApp::GetPlaceableByGameObjectID (0x4AE7A0). Every other value is a
// plain memory read through a fallible reader. There is no write API here.
// Evidence: /home/brunner56/kp-live-20260922/motion-m0-rederivation.md and
// motion-m0-verification.md (verdict CONFIRMS); only its "safe" list is used.
#include "api/model.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
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
    Address placeable_vtable;   // CSWSPlaceable vtable
    std::uint8_t placeable_type;// CGameObject type byte for a placeable
    unsigned id, type;          // CGameObject
    unsigned area_id, position, orientation;         // CSWSObject
    unsigned push_gate, dirty;                       // CSWSObject
    unsigned aabb_marker, quaternion;                // CSWSPlaceable
    std::array<Span, 24> spans; // unused tail entries have va 0
    std::array<Slot, 4> slots;
};
const std::array<Profile, 1>& profiles();
const Profile* profile_for(const std::string& sha);

// Closed set of failure kinds. Identity covers "not a placeable": null lookup,
// wrong type byte, wrong vtable or an id that does not round-trip.
enum class Failure { None, Unsupported, Guard, Chain, Identity, Value };
const char* failure_name(Failure);

struct Backend {
    virtual ~Backend() = default;
    virtual Abi abi() const = 0;
    virtual unsigned width() const = 0;
    virtual bool read(Address, void*, std::size_t) const = 0;
    // thiscall(CServerExoApp*, uint32 id) -> CSWSPlaceable* or 0.
    virtual Address placeable(Address function, Address server, std::uint32_t id) = 0;
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
};
class Operations {
public:
    bool bind(const std::string& verified_sha, Address loaded_base, Backend*, std::string& error);
    void unbind();
    bool available() const { return backend_ != nullptr; }
    const Profile* profile() const { return profile_; }
    std::uint64_t epoch() const { return epoch_; }
    // Fills out only on success; on failure out is left untouched.
    bool capture(std::uint32_t id, Capture& out, std::string& error);
    Failure last_failure() const { return failure_; }
    static bool valid_span(const Span&);
private:
    bool fail(Failure, std::string& error, const std::string& text);
    bool guards(std::string& error);
    bool pointer(Address, Address&) const;
    Address at(Address va) const { return loaded_base_ + va - profile_->preferred_base; }
    const Profile* profile_ = nullptr;
    Backend* backend_ = nullptr;
    Address loaded_base_ = 0;
    std::uint64_t epoch_ = 0;
    Failure failure_ = Failure::None;
};
Operations& operations();
Backend* native_backend(model::Reader, void* context);
bool bind_native(const std::string& verified_sha, Address loaded_base, model::Reader, void*, std::string&);
void register_all(lua_State*);
} // namespace kp::api::motion
