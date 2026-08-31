#include "events/payload.hpp"

#include <cstring>

#include "platform/platform.hpp"

namespace kp::events {
namespace {

// CExoArrayList {void* data; int32 size; int32 capacity}. sizeof == 0xC.
struct ArrayList {
    const void*   data;
    std::int32_t  size;
    std::int32_t  capacity;
};
static_assert(sizeof(ArrayList) == 12, "CExoArrayList is three 32-bit fields");

// CScriptEvent, 52 bytes. See docs/event-semantics.md -- not the older
// "three of each" reading, and not the phasor_structs fixed-slot layout.
constexpr std::size_t kEventSize     = 0x34;
constexpr std::size_t kOffType       = 0x00;
constexpr std::size_t kOffInts       = 0x04;
constexpr std::size_t kOffFloats     = 0x10;
constexpr std::size_t kOffStrings    = 0x1C;
constexpr std::size_t kOffObjects    = 0x28;

// CGameObject.id is at +4. CSWSArea embeds that header at +284.
constexpr std::size_t kIdOffset         = 4;
constexpr std::size_t kAreaGameObject   = 284;
constexpr std::size_t kModuleGameObject = 28;  // pointer, medium confidence

struct ExoString {
    const char*   c_string;
    std::uint32_t length;
};

bool readable(const void* p, std::size_t n) {
    return p != nullptr && platform::is_readable(p, n);
}

const std::uint8_t* bytes(const ScriptEventView& ev) {
    return static_cast<const std::uint8_t*>(ev.data);
}

bool event_ok(const ScriptEventView& ev) {
    return readable(ev.data, kEventSize);
}

bool read_list(const ScriptEventView& ev, std::size_t off, ArrayList& out) {
    if (!event_ok(ev)) return false;
    std::memcpy(&out, bytes(ev) + off, sizeof out);
    return true;
}

template <typename T>
T slot_or(const ScriptEventView& ev, std::size_t list_off, int index, T fallback) {
    if (index < 0) return fallback;
    ArrayList list{};
    if (!read_list(ev, list_off, list)) return fallback;
    if (index >= list.size) return fallback;
    if (list.data == nullptr) return fallback;
    const std::size_t nbytes = sizeof(T) * static_cast<std::size_t>(index + 1);
    if (!readable(list.data, nbytes)) return fallback;
    T value{};
    std::memcpy(&value, static_cast<const std::uint8_t*>(list.data) +
                            sizeof(T) * static_cast<std::size_t>(index),
                sizeof(T));
    return value;
}

std::uint32_t read_u32(const void* p, std::size_t off) {
    const auto* base = static_cast<const std::uint8_t*>(p);
    if (!readable(base + off, 4)) return kObjectInvalid;
    std::uint32_t v = 0;
    std::memcpy(&v, base + off, 4);
    return v;
}

void* read_ptr(const void* p, std::size_t off) {
    const auto* base = static_cast<const std::uint8_t*>(p);
    if (!readable(base + off, sizeof(void*))) return nullptr;
    void* v = nullptr;
    std::memcpy(&v, base + off, sizeof(void*));
    return v;
}

bool parse_indexed(std::string_view source, std::string_view prefix, int& index) {
    if (source.size() < prefix.size() + 2) return false;
    if (source.substr(0, prefix.size()) != prefix) return false;
    if (source.back() != ']') return false;
    const std::string_view num = source.substr(prefix.size(),
                                               source.size() - prefix.size() - 1);
    if (num.empty()) return false;
    int n = 0;
    for (char c : num) {
        if (c < '0' || c > '9') return false;
        n = n * 10 + (c - '0');
    }
    index = n;
    return true;
}

}  // namespace

int script_event_type(const ScriptEventView& ev) {
    if (!event_ok(ev)) return -1;
    std::uint16_t t = 0;
    std::memcpy(&t, bytes(ev) + kOffType, sizeof t);
    return static_cast<int>(t);
}

int script_event_int(const ScriptEventView& ev, int index) {
    return slot_or<int>(ev, kOffInts, index, 0);
}

float script_event_float(const ScriptEventView& ev, int index) {
    return slot_or<float>(ev, kOffFloats, index, 0.0f);
}

std::uint32_t script_event_object(const ScriptEventView& ev, int index) {
    return slot_or<std::uint32_t>(ev, kOffObjects, index, kObjectInvalid);
}

std::string script_event_string(const ScriptEventView& ev, int index) {
    if (index < 0) return {};
    ArrayList list{};
    if (!read_list(ev, kOffStrings, list)) return {};
    if (index >= list.size || list.data == nullptr) return {};
    const std::size_t nbytes = sizeof(ExoString) * static_cast<std::size_t>(index + 1);
    if (!readable(list.data, nbytes)) return {};
    ExoString s{};
    std::memcpy(&s, static_cast<const std::uint8_t*>(list.data) +
                        sizeof(ExoString) * static_cast<std::size_t>(index),
                sizeof s);
    if (s.c_string == nullptr || s.length == 0) return {};
    constexpr std::uint32_t kMax = 64 * 1024;
    if (s.length > kMax || !readable(s.c_string, s.length)) return {};
    std::uint32_t len = s.length;
    if (len > 0 && s.c_string[len - 1] == '\0') --len;
    return std::string(s.c_string, len);
}

bool payload_is_script_event(int outer_event_id) {
    return outer_event_id == kSignalEvent ||
           outer_event_id == 0x18 ||
           outer_event_id == 0x1A;
}

std::uint32_t object_id_from_handler(void* self, std::string_view hook_site) {
    if (self == nullptr) return kObjectInvalid;
    if (hook_site == "event.area")
        return read_u32(self, kAreaGameObject + kIdOffset);
    if (hook_site == "event.module") {
        if (void* go = read_ptr(self, kModuleGameObject))
            return read_u32(go, kIdOffset);
        return kObjectInvalid;
    }
    return read_u32(self, kIdOffset);
}

std::vector<lua::Value> shape_handler_args(const EventContract& ev,
                                           const HandlerFrame& frame) {
    ScriptEventView payload;
    if (payload_is_script_event(frame.outer_event_id))
        payload.data = frame.payload;

    std::vector<lua::Value> out;
    out.reserve(ev.args.size());
    for (const Argument& a : ev.args) {
        const std::string& src = a.source;
        int index = 0;
        if (src == "this") {
            out.push_back(lua::Value::object(
                object_id_from_handler(frame.self, frame.hook_site)));
        } else if (src == "caller") {
            out.push_back(lua::Value::object(frame.caller));
        } else if (src == "calendar_day") {
            out.push_back(lua::Value::integer(frame.calendar_day));
        } else if (src == "time_of_day") {
            out.push_back(lua::Value::integer(frame.time_of_day));
        } else if (parse_indexed(src, "int_params[", index)) {
            out.push_back(lua::Value::integer(script_event_int(payload, index)));
        } else if (parse_indexed(src, "float_params[", index)) {
            out.push_back(lua::Value::number(script_event_float(payload, index)));
        } else if (parse_indexed(src, "object_params[", index)) {
            out.push_back(lua::Value::object(script_event_object(payload, index)));
        } else if (parse_indexed(src, "string_params[", index)) {
            out.push_back(lua::Value::str(script_event_string(payload, index)));
        } else {
            out.push_back(lua::Value::none());
        }
    }
    return out;
}

}  // namespace kp::events
