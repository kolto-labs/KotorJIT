#include "api/motion.hpp"
#include <cmath>
#include <cstring>
// Checked core for kp.motion M1. Order on every capture:
//   profile bound -> exact guards (spans + vtable slots) -> id sentinel ->
//   server lookup chain -> typed getter (the only engine call) ->
//   fences (vtable, type byte, id round-trip) -> field reads -> finite checks.
// Nothing is written to the caller's Capture until every step has passed.
namespace kp::api::motion {
namespace {
constexpr std::uint32_t object_invalid = 0x7f000000;
int digit(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}
}
Operations& operations() { static Operations o; return o; }

void Operations::unbind() { backend_ = nullptr; profile_ = nullptr; loaded_base_ = 0; ++epoch_; }

bool Operations::fail(Failure f, std::string& error, const std::string& text) {
    failure_ = f;
    error = std::string(failure_name(f)) + ": " + text;
    return false;
}

bool Operations::valid_span(const Span& s) {
    if (!s.hex) return false;
    std::size_t n = std::strlen(s.hex);
    if (n == 0 || n % 2 || n / 2 > max_span_bytes) return false;
    for (std::size_t i = 0; i < n; ++i) if (digit(s.hex[i]) < 0) return false;
    return true;
}

bool Operations::guards(std::string& error) {
    if (!backend_ || !profile_) return fail(Failure::Unsupported, error, "no verified native motion binding");
    for (const auto& s : profile_->spans) {
        if (!s.va) continue;
        if (!valid_span(s)) return fail(Failure::Guard, error, "invalid guard span in profile");
        std::size_t n = std::strlen(s.hex) / 2;
        unsigned char actual[max_span_bytes]{};
        if (!backend_->read(at(s.va), actual, n)) return fail(Failure::Guard, error, "guard bytes unreadable");
        for (std::size_t j = 0; j < n; ++j)
            if (actual[j] != ((digit(s.hex[j * 2]) << 4) | digit(s.hex[j * 2 + 1])))
                return fail(Failure::Guard, error, "code guard mismatch");
    }
    for (const auto& s : profile_->slots) {
        if (!s.va) continue;
        Address target = 0;
        if (!pointer(at(s.va), target) || target != at(s.target))
            return fail(Failure::Guard, error, "placeable vtable slot mismatch");
    }
    return true;
}

bool Operations::bind(const std::string& sha, Address base, Backend* backend, std::string& error) {
    unbind(); error.clear(); failure_ = Failure::None;
    const Profile* p = profile_for(sha);
    if (!p) return fail(Failure::Unsupported, error, "unknown executable SHA256");
    if (!backend || backend->abi() != p->abi || backend->width() != p->width)
        return fail(Failure::Unsupported, error, "motion OS/ABI/pointer width mismatch");
    if (!base) return fail(Failure::Unsupported, error, "invalid loaded-image base");
    // Guards embed absolute immediates (g_pAppManager, the type constant and
    // the vtable), so a relocated image cannot match them.
    if (base != p->preferred_base) return fail(Failure::Unsupported, error, "relocated image: absolute guards cannot match");
    profile_ = p; backend_ = backend; loaded_base_ = base;
    if (!guards(error)) { Failure f = failure_; unbind(); failure_ = f; return false; }
    failure_ = Failure::None;
    return true;
}

bool Operations::pointer(Address address, Address& value) const {
    value = 0;
    std::uint32_t n = 0;
    if (!backend_->read(address, &n, 4)) return false;
    value = n;
    return value != 0;
}

bool Operations::capture(std::uint32_t id, Capture& out, std::string& error) {
    error.clear();
    if (!guards(error)) return false;
    if (id == object_invalid) return fail(Failure::Identity, error, "OBJECT_INVALID is not a placeable");
    const Profile& p = *profile_;
    Address manager = 0, server = 0, internal = 0, array = 0;
    std::uint8_t probe = 0;
    if (!pointer(at(p.manager_slot), manager) || !pointer(manager + p.manager_server, server) ||
        !pointer(server + p.server_internal, internal) || !pointer(internal + p.internal_array, array) ||
        !backend_->read(array, &probe, 1))
        return fail(Failure::Chain, error, "server object array unavailable");

    Address object = backend_->placeable(at(p.get_placeable), server, id);
    if (!object) return fail(Failure::Identity, error, "no server placeable with that ID");
    Address vtable = 0; std::uint8_t type = 0; std::uint32_t actual = 0;
    if (!pointer(object, vtable) || vtable != at(p.placeable_vtable))
        return fail(Failure::Identity, error, "object vtable is not CSWSPlaceable");
    if (!backend_->read(object + p.type, &type, 1) || type != p.placeable_type)
        return fail(Failure::Identity, error, "object type byte is not placeable");
    if (!backend_->read(object + p.id, &actual, 4) || actual != id)
        return fail(Failure::Identity, error, "object ID does not round-trip");

    Capture c;
    std::uint32_t dirty = 0; std::int32_t marker = 0;
    if (!backend_->read(object + p.area_id, &c.area_id, 4) ||
        !backend_->read(object + p.position, c.position.data(), 12) ||
        !backend_->read(object + p.orientation, c.orientation.data(), 12) ||
        !backend_->read(object + p.push_gate, &c.push_gate_raw, 4) ||
        !backend_->read(object + p.dirty, &dirty, 4) ||
        !backend_->read(object + p.aabb_marker, &marker, 4) ||
        !backend_->read(object + p.quaternion, c.quaternion_raw.data(), 16))
        return fail(Failure::Chain, error, "placeable fields unreadable");
    for (float v : c.position) if (!std::isfinite(v)) return fail(Failure::Value, error, "position is not finite");
    for (float v : c.orientation) if (!std::isfinite(v)) return fail(Failure::Value, error, "orientation is not finite");
    for (float v : c.quaternion_raw) if (!std::isfinite(v)) return fail(Failure::Value, error, "quaternion is not finite");
    double deg = std::atan2(static_cast<double>(c.orientation[1]), static_cast<double>(c.orientation[0])) * 180.0 / 3.14159265358979323846;
    if (deg < 0) deg += 360.0;
    // Wrap after the cast: 360 - 5.7e-6 rounds to 360.0f in float.
    float facing = static_cast<float>(deg);
    if (facing >= 360.f || facing < 0.f) facing = 0.f;
    c.facing = facing;
    c.epoch = epoch_; c.id = id; c.object = object;
    c.dirty_position = (dirty & dirty_position_bit) != 0;
    c.dirty_orientation = (dirty & dirty_orientation_bit) != 0;
    c.collision_registered = marker >= 0;
    out = c;
    failure_ = Failure::None;
    return true;
}
} // namespace kp::api::motion
