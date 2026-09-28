#include "api/camera.hpp"
#include <cmath>
#include <cstdio>
#include <cstring>
namespace kp::api::camera {
namespace {
int nibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}
std::string hex(Address value) {
    char text[24];
    std::snprintf(text, sizeof text, "0x%llx", static_cast<unsigned long long>(value));
    return text;
}
}
Operations& operations() { static Operations value; return value; }

bool Operations::fail(Failure kind, std::string& error, const std::string& text) {
    failure_ = kind; error = text; return false;
}
void Operations::unbind() { backend_ = nullptr; profile_ = nullptr; loaded_base_ = 0; ++epoch_; }

bool Operations::valid_span(const Span& s) {
    if (!s.hex) return false;
    const std::size_t n = std::strlen(s.hex);
    if (n == 0 || n % 2 || n / 2 > max_span_bytes) return false;
    for (std::size_t i = 0; i < n; ++i) if (nibble(s.hex[i]) < 0) return false;
    return true;
}

// Every span and vtable slot, compared exactly. Called at bind and before
// every snapshot, so a patched or swapped image never yields a read.
bool Operations::guards(std::string& error) {
    if (!backend_ || !profile_) return fail(Failure::Unsupported, error, "unsupported: no verified native camera binding");
    for (const auto& s : profile_->spans) {
        if (!s.va) continue;
        if (!valid_span(s)) return fail(Failure::Guard, error, "guard: malformed camera span at " + hex(s.va));
        const std::size_t n = std::strlen(s.hex) / 2;
        unsigned char expected[max_span_bytes], actual[max_span_bytes];
        for (std::size_t j = 0; j < n; ++j)
            expected[j] = static_cast<unsigned char>((nibble(s.hex[j * 2]) << 4) | nibble(s.hex[j * 2 + 1]));
        if (!backend_->read(at(s.va), actual, n) || std::memcmp(expected, actual, n) != 0)
            return fail(Failure::Guard, error, "guard: camera code guard mismatch at " + hex(s.va));
    }
    for (const auto& s : profile_->slots) {
        if (!s.va) continue;
        Address word = 0;
        if (!pointer(at(s.va), word) || word != at(s.target))
            return fail(Failure::Guard, error, "guard: camera vtable slot mismatch at " + hex(s.va));
    }
    failure_ = Failure::None;
    return true;
}

bool Operations::bind(const std::string& sha, Address base, Backend* backend, std::string& error) {
    unbind(); error.clear();
    const Profile* p = profile_for(sha);
    if (!p) return fail(Failure::Unsupported, error, "unsupported: no camera profile for this executable");
    if (!backend || backend->abi() != p->abi || backend->width() != p->width)
        return fail(Failure::Unsupported, error, "unsupported: camera OS/ABI/pointer width mismatch");
    if (!base) return fail(Failure::Unsupported, error, "unsupported: invalid loaded-image base");
    // Guards embed absolute immediates (vtable stores, global loads), so a
    // relocated image cannot match them. Refuse rather than rebase.
    if (base != p->preferred_base)
        return fail(Failure::Unsupported, error, "unsupported: relocated image base " + hex(base));
    profile_ = p; backend_ = backend; loaded_base_ = base;
    if (!guards(error)) { Failure f = failure_; unbind(); failure_ = f; return false; }
    return true;
}

bool Operations::pointer(Address address, Address& value) const {
    std::uint32_t n = 0; value = 0;
    if (!backend_->read(address, &n, 4)) return false;
    value = n;
    return value != 0;
}

bool Operations::snapshot(Capture& out, std::string& error) {
    out = {}; error.clear();
    if (!guards(error)) return false;
    const Profile& p = *profile_;
    Address manager = 0, client = 0, internal = 0, module = 0, options = 0, camera = 0, behavior = 0, vtable = 0;
    auto chain = [&](const char* hop) { return fail(Failure::Chain, error, std::string("chain: ") + hop + " unavailable"); };
    if (!pointer(at(p.manager_slot), manager)) return chain("app manager");
    if (!pointer(manager + p.manager_client, client)) return chain("client");
    if (!pointer(client + p.client_internal, internal)) return chain("client internal");
    if (!pointer(internal + p.internal_module, module) || !pointer(module, vtable)) return chain("module");
    if (vtable != at(p.module_vtable))
        return fail(Failure::Guard, error, "guard: module vtable " + hex(vtable) + " is not " + hex(at(p.module_vtable)));
    std::uint8_t mode = 0;
    if (!pointer(internal + p.internal_options, options) || !backend_->read(options + p.options_mode, &mode, 1))
        return chain("options");
    if (!pointer(module + p.module_camera, camera) || !pointer(camera, vtable)) return chain("camera");
    if (vtable != at(p.camera_vtable))
        return fail(Failure::Guard, error, "guard: camera vtable " + hex(vtable) + " is not " + hex(at(p.camera_vtable)));
    std::int32_t pending = 0;
    if (!backend_->read(at(p.pending_style), &pending, 4)) return chain("pending style");
    if (!pointer(camera + p.camera_behavior, behavior) || !pointer(behavior, vtable)) return chain("behaviour");

    Capture c;
    c.epoch = epoch_; c.module = module; c.camera = camera; c.behavior_ptr = behavior; c.behavior_vtable = vtable;
    c.mode = mode; c.pending_style = pending;
    // Only the exact chase vtable (whose TypeId slot the guards pin to 0x106a)
    // makes the chase offsets meaningful. Any other behaviour reads nothing more.
    if (vtable != at(p.chase_vtable)) { c.behavior = Behavior::Other; out = c; return true; }
    c.behavior = Behavior::Chase;
    auto f32 = [&](unsigned offset, float& value) { return backend_->read(behavior + offset, &value, 4); };
    bool read = f32(p.dist, c.distance) && f32(p.speed, c.speed) && f32(p.pitch, c.pitch) && f32(p.height, c.height) &&
        backend_->read(behavior + p.dolly, &c.dolly, 4) && f32(p.base_distance, c.base_distance) &&
        f32(p.base_view_angle, c.base_view_angle) && backend_->read(behavior + p.style_row, &c.style_row, 4);
    for (unsigned i = 0; read && i < 4; ++i) read = f32(p.raw_28 + i * 4, c.raw_28[i]);
    for (unsigned i = 0; read && i < 3; ++i) read = f32(p.raw_38 + i * 4, c.raw_38[i]) && f32(p.raw_50 + i * 4, c.raw_50[i]);
    if (!read) return chain("chase field");
    bool finite = std::isfinite(c.distance) && std::isfinite(c.speed) && std::isfinite(c.pitch) &&
        std::isfinite(c.height) && std::isfinite(c.base_distance) && std::isfinite(c.base_view_angle);
    for (float v : c.raw_28) finite = finite && std::isfinite(v);
    for (float v : c.raw_38) finite = finite && std::isfinite(v);
    for (float v : c.raw_50) finite = finite && std::isfinite(v);
    if (!finite) return fail(Failure::Value, error, "value: non-finite chase camera float");
    out = c;
    return true;
}
} // namespace kp::api::camera
