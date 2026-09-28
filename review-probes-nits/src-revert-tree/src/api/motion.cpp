#include "api/motion.hpp"
#include "api/engine_gate.hpp"
#include <atomic>
#include <cmath>
#include <cstring>
// Checked core for kp.motion. Order on every capture:
//   profile bound -> engine-thread gate -> exact guards (spans + vtable
//   slots) -> id sentinel -> server lookup chain -> typed getter ->
//   fences (vtable, type byte, id round-trip) -> field reads -> finite checks.
// Nothing is written to the caller's Capture until every step has passed.
// relocate/restore follow motion-m2-plan.md section 4 (R1..R12); the only
// engine write is one SetPosition(pos, 1, 1, 0) per successful call.
namespace kp::api::motion {
namespace {
constexpr std::uint32_t object_invalid = 0x7f000000;
std::atomic<TickSource> g_tick{nullptr};
std::atomic<void*> g_tick_context{nullptr};
bool is_nan(std::uint32_t bits) { return (bits & 0x7f800000u) == 0x7f800000u && (bits & 0x007fffffu) != 0; }
double distance(const std::array<float, 3>& a, const std::array<float, 3>& b) {
    double x = double(a[0]) - b[0], y = double(a[1]) - b[1], z = double(a[2]) - b[2];
    return std::sqrt(x * x + y * y + z * z);
}
int digit(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return c - 'a' + 10;
    return -1;
}
}
Operations& operations() { static Operations o; return o; }

bool bit_equal(const std::array<float, 3>& a, const std::array<float, 3>& b) {
    return std::memcmp(a.data(), b.data(), sizeof(float) * 3) == 0;
}
bool engine_equal(const std::array<float, 3>& a, const std::array<float, 3>& b) {
    for (int i = 0; i < 3; ++i) {
        std::uint32_t x = 0, y = 0;
        std::memcpy(&x, &a[i], 4); std::memcpy(&y, &b[i], 4);
        if (is_nan(x) || is_nan(y)) return false;
        if (x == y) continue;
        if (((x | y) & 0x7fffffffu) == 0) continue;   // +0 == -0
        return false;
    }
    return true;
}
void bind_tick(TickSource source, void* context) {
    g_tick.store(nullptr); g_tick_context.store(context); g_tick.store(source);
}
bool current_tick(std::uint64_t& out) {
    TickSource source = g_tick.load();
    if (!source) return false;
    out = source(g_tick_context.load());
    return true;
}

// Unbind drops the ledger: entries name a binding epoch that no longer
// exists, and keeping them would lock their objects forever.
void Operations::unbind() { backend_ = nullptr; profile_ = nullptr; loaded_base_ = 0; ++epoch_; ledger_.clear(); }

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
    if (!backend_ || !profile_) return fail(Failure::Unsupported, error, "no verified native motion binding");
    if (!engine::on_engine_thread()) return fail(Failure::Unsupported, error, "not on the engine thread");
    return locate(id, out, error);
}

bool Operations::locate(std::uint32_t id, Capture& out, std::string& error) {
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
    return read_fields(object, id, out, error);
}

bool Operations::read_fields(Address object, std::uint32_t id, Capture& out, std::string& error) {
    const Profile& p = *profile_;
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

// One SetPosition(object, &target, 1, 1, 0), then raw readback on the same
// pointer (no second getter call). Readback contract (plan section 1):
// position bit-equal to the target, dirty position bit set, id/vtable/type
// and area unchanged. landed receives the readback position when it could be
// read, otherwise the target.
bool Operations::write_and_verify(const Capture& before, const std::array<float, 3>& target, Capture& out,
                                  std::string& error) {
    backend_->set_position(at(profile_->set_position), before.object, target, 1, 1, 0);
    Capture after; std::string why;
    out = before; out.position = target;
    if (!read_fields(before.object, before.id, after, why))
        return fail(Failure::Mutation, error, "readback failed after the write (" + why + "); the write may have happened");
    out = after;
    if (after.area_id != before.area_id)
        return fail(Failure::Mutation, error, "area changed across the write; the write may have happened");
    if (!bit_equal(after.position, target))
        return fail(Failure::Mutation, error, "readback mismatch; the write may have happened");
    if (!after.dirty_position)
        return fail(Failure::Mutation, error, "position dirty bit not set after the write; the write may have happened");
    failure_ = Failure::None;
    return true;
}

bool Operations::relocate(std::uint64_t token, Writer writer, const Capture& from, const std::array<float, 3>& target,
                          bool allow_stale_collision, Capture& out, Status& status, std::string& error) {
    error.clear();
    // R1, R2: no reads, no calls.
    if (!backend_ || !profile_) return fail(Failure::Unsupported, error, "no verified native motion binding");
    if (!engine::on_engine_thread()) return fail(Failure::Unsupported, error, "not on the engine thread");
    // R3
    if (writer != Writer::Loaded || token == 0)
        return fail(Failure::Unsupported, error, "only a loaded script can move placeables");
    // R4: pure argument checks. The capture epoch needs no read, so a capture
    // from an earlier binding is refused here, before the getter.
    for (float v : target) if (!std::isfinite(v)) return fail(Failure::Value, error, "target is not finite");
    if (from.epoch != epoch_ || from.object == 0)
        return fail(Failure::Stale, error, "capture is from an earlier motion binding; capture again");
    // R5, R6: guards, chain, getter, fences.
    Capture cur;
    if (!locate(from.id, cur, error)) return false;
    if (cur.object != from.object) return fail(Failure::Identity, error, "object pointer changed since the capture");
    // R7
    if (cur.area_id == object_invalid || cur.area_id == 0)
        return fail(Failure::Stale, error, "placeable is not in an area");
    if (cur.area_id != from.area_id) return fail(Failure::Stale, error, "area changed since the capture");
    if (!bit_equal(cur.position, from.position) || !bit_equal(cur.orientation, from.orientation))
        return fail(Failure::Stale, error, "pose changed since the capture; pass the latest capture");
    // R8
    if (cur.collision_registered && !allow_stale_collision)
        return fail(Failure::Collision, error, "placeable has a registered walkmesh; a raw move leaves it behind");
    // R9 (policy). The origin is this token's recorded origin, or the current pose.
    auto it = ledger_.find(from.id);
    Entry* mine = (it != ledger_.end() && it->second.owner_token == token) ? &it->second : nullptr;
    const std::array<float, 3>& origin = mine ? mine->origin_position : cur.position;
    for (float v : target) if (std::fabs(double(v)) > max_coord) return fail(Failure::Bounds, error, "target coordinate beyond 1e5");
    if (distance(target, cur.position) > max_step) return fail(Failure::Bounds, error, "step longer than 5.0 m");
    if (std::fabs(double(target[2]) - cur.position[2]) > max_dz) return fail(Failure::Bounds, error, "height change larger than 1.0 m");
    if (distance(target, origin) > max_from_origin) return fail(Failure::Bounds, error, "target farther than 25.0 m from the origin");
    // R10
    if (it != ledger_.end() && !mine) return fail(Failure::Owned, error, "object is moved by another script");
    // Our own entry must still describe this object at the pose we last wrote;
    // otherwise someone else moved it and a later restore would clobber that.
    if (mine && (mine->object != cur.object || mine->area_id != cur.area_id ||
                 mine->binding_epoch != epoch_ || !bit_equal(cur.position, mine->last_written))) {
        ledger_.erase(it);
        return fail(Failure::Conflict, error, "moved by another writer; ownership released");
    }
    // R11: the engine's own early return (0x4AA980). No setter call.
    if (engine_equal(target, cur.position)) {
        cur.owned = mine != nullptr;
        out = cur; status = Status::Noop; failure_ = Failure::None;
        return true;
    }
    // Record the entry before the write so a mutation still leaves a
    // restorable origin (plan section 1).
    if (!mine) {
        Entry e;
        e.owner_token = token; e.binding_epoch = epoch_; e.object = cur.object; e.area_id = cur.area_id;
        e.origin_position = cur.position; e.origin_orientation = cur.orientation;
        e.last_written = cur.position;
        mine = &(ledger_[from.id] = e);
    }
    Capture after;
    bool ok = write_and_verify(cur, target, after, error);
    mine->last_written = after.position;
    ++mine->writes;
    std::uint64_t tick = 0;
    if (current_tick(tick)) { mine->has_tick = true; mine->last_write_tick = tick; }
    if (!ok) return false;   // R12: Mutation, entry kept
    after.owned = true;
    out = after; status = Status::Moved;
    return true;
}

bool Operations::restore(std::uint64_t token, Writer writer, std::uint32_t id, Capture& out, std::string& error) {
    error.clear();
    if (!backend_ || !profile_) return fail(Failure::Unsupported, error, "no verified native motion binding");
    if (!engine::on_engine_thread()) return fail(Failure::Unsupported, error, "not on the engine thread");
    // R3 without the staged half: an owner can always put things back.
    if (writer == Writer::None || token == 0)
        return fail(Failure::Unsupported, error, "only a loaded script can move placeables");
    auto it = ledger_.find(id);
    if (it == ledger_.end() || it->second.owner_token != token)
        return fail(Failure::NotOwner, error, "object is not moved by this script");
    Entry& e = it->second;
    Capture cur;
    if (!locate(id, cur, error)) {
        // Guards and the chain can be transient: keep ownership. Anything
        // else means the object is gone or is not what we moved.
        if (failure_ == Failure::Guard || failure_ == Failure::Chain) return false;
        Failure f = failure_; std::string why = error;
        ledger_.erase(it);
        error = why + "; ownership released"; failure_ = f;
        return false;
    }
    auto release = [&](Failure f, const char* text) {
        ledger_.erase(it);
        return fail(f, error, std::string(text) + "; ownership released");
    };
    if (e.binding_epoch != epoch_) return release(Failure::Stale, "motion binding changed");
    if (cur.object != e.object) return release(Failure::Identity, "object pointer changed");
    if (cur.area_id != e.area_id) return release(Failure::Stale, "area changed");
    // Fence 6, plus the orientation M2 never writes.
    if (!bit_equal(cur.position, e.last_written) || !bit_equal(cur.orientation, e.origin_orientation))
        return release(Failure::Conflict, "moved by another writer");
    if (engine_equal(e.origin_position, cur.position)) {
        ledger_.erase(it);
        cur.owned = false; out = cur; failure_ = Failure::None;
        return true;
    }
    Capture after;
    if (!write_and_verify(cur, e.origin_position, after, error)) {
        e.last_written = after.position;
        ++e.writes;
        std::uint64_t tick = 0;
        if (current_tick(tick)) { e.has_tick = true; e.last_write_tick = tick; }
        return false;
    }
    ledger_.erase(it);
    after.owned = false;
    out = after;
    return true;
}

bool Operations::observe(std::uint32_t id, Address expected_object, Observation& out, std::string& error) {
    error.clear();
    if (!backend_ || !profile_) return fail(Failure::Unsupported, error, "no verified native motion binding");
    if (!engine::on_engine_thread()) return fail(Failure::Unsupported, error, "not on the engine thread");
    Capture cur;
    if (!locate(id, cur, error)) return false;
    if (cur.object != expected_object) return fail(Failure::Identity, error, "object pointer changed since the capture");
    Observation o;
    o.push_gate_raw = cur.push_gate_raw;
    o.dirty_position = cur.dirty_position;
    o.pushed = !cur.dirty_position && cur.push_gate_raw != 0;
    auto it = ledger_.find(id);
    if (it != ledger_.end()) {
        o.has_write = true;
        std::uint64_t now = 0;
        if (it->second.has_tick && current_tick(now) && now >= it->second.last_write_tick) {
            o.has_tick = true; o.ticks_since_write = now - it->second.last_write_tick;
        }
    }
    out = o; failure_ = Failure::None;
    return true;
}

std::uint64_t Operations::owner_of(std::uint32_t id) const {
    auto it = ledger_.find(id);
    return it == ledger_.end() ? 0 : it->second.owner_token;
}
const Entry* Operations::entry(std::uint32_t id) const {
    auto it = ledger_.find(id);
    return it == ledger_.end() ? nullptr : &it->second;
}
} // namespace kp::api::motion
