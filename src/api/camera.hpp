#pragma once
// kp.camera Stage 1: read-only snapshot of the client chase camera.
// Pure memory reads through a fallible reader. The Backend has no call method,
// so no engine function is reachable from this module.
#include "api/model.hpp"
#include <array>
#include <cstddef>
#include <cstdint>
#include <string>

struct lua_State;
namespace kp::api::camera {
using Address = std::uint64_t;
using model::Abi;
// Exact byte guard: an instruction or literal whose bytes pin an offset,
// global or vtable. Hex is lowercase, even length, 1..16 bytes.
struct Span { Address va; const char* hex; };
constexpr std::size_t max_span_bytes = 16;
// A vtable slot that must hold the given function VA.
struct Slot { Address va; Address target; };
struct Profile {
    const char* name; const char* sha256; Abi abi; unsigned width; Address preferred_base;
    Address manager_slot;          // g_pAppManager
    unsigned manager_client;       // CAppManager::client
    unsigned client_internal;      // CClientExoApp::internal
    unsigned internal_module;      // CClientExoAppInternal::module
    unsigned internal_options;     // CClientExoAppInternal::options
    unsigned options_mode;         // CClientOptions::camera_mode (byte)
    unsigned module_camera;        // CSWCModule::camera
    unsigned camera_behavior;      // CAurCamera::active_behavior
    Address module_vtable, camera_vtable, chase_vtable;
    std::uint32_t chase_type_id;
    Address pending_style;         // global, int32, -1 = none
    // CSWCameraOnAStick fields.
    unsigned dist, speed, pitch, height, dolly, base_distance, base_view_angle, style_row;
    unsigned raw_28, raw_38, raw_50; // offsets verified, meaning unverified
    std::array<Span, 32> spans;    // unused tail entries have va 0
    std::array<Slot, 4> slots;
};
const std::array<Profile, 1>& profiles();
const Profile* profile_for(const std::string& sha);

// Closed set of failure kinds.
enum class Failure { None, Unsupported, Guard, Chain, Value };
const char* failure_name(Failure);

struct Backend {
    virtual ~Backend() = default;
    virtual Abi abi() const = 0;
    virtual unsigned width() const = 0;
    virtual bool read(Address, void*, std::size_t) const = 0;
};
enum class Behavior { Chase, Other };
struct Capture {
    std::uint64_t epoch = 0;
    Address module = 0, camera = 0, behavior_ptr = 0, behavior_vtable = 0;
    std::uint8_t mode = 0;
    std::int32_t pending_style = -1;
    Behavior behavior = Behavior::Other;
    // Present only when behavior == Chase.
    float distance = 0, speed = 0, pitch = 0, height = 0;
    std::uint32_t dolly = 0;
    float base_distance = 0, base_view_angle = 0;
    std::int32_t style_row = -1;
    std::array<float, 4> raw_28{};
    std::array<float, 3> raw_38{}, raw_50{};
};
class Operations {
public:
    bool bind(const std::string& verified_sha, Address loaded_base, Backend*, std::string& error);
    void unbind();
    bool available() const { return backend_ != nullptr; }
    const Profile* profile() const { return profile_; }
    std::uint64_t epoch() const { return epoch_; }
    bool snapshot(Capture&, std::string& error);
    Failure last_failure() const { return failure_; }
    // Offline validation of a span table (length cap and hex syntax).
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
} // namespace kp::api::camera
