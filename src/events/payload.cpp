#include "events/payload.hpp"

#include <cstddef>
#include <cstring>

#include "api/abi_layout.hpp"
#include "platform/platform.hpp"
#include "platform/target.hpp"

namespace kp::events {
namespace {

namespace L = kp::api::layout;

// CExoArrayList {void* data; int32 size; int32 capacity}: 0xC bytes on i386,
// 0x10 on x86_64 (size at +8). Natural alignment gives exactly that layout.
struct ArrayList {
    const void*   data;
    std::int32_t  size;
    std::int32_t  capacity;
};
static_assert(sizeof(ArrayList) == L::kEngine.arraylist_bytes, "CExoArrayList width");
static_assert(offsetof(ArrayList, size) == L::kEngine.arraylist_size_field, "CExoArrayList size field");

// CScriptEvent. i386: 52 bytes (docs/event-semantics.md -- not the older
// "three of each" reading, and not the phasor_structs fixed-slot layout).
// x86_64: 0x48 bytes, the same four lists at 16-byte strides; object ids are
// 8-byte elements there. Values in api/abi_layout.hpp, x86_64 ones verified
// against both Mac images by tools/mac/gen_mac_tables.py.
constexpr std::size_t kEventSize     = L::kEngine.script_event_bytes;
constexpr std::size_t kOffType       = 0x00;
constexpr std::size_t kOffInts       = L::kEngine.script_event_ints;
constexpr std::size_t kOffFloats     = L::kEngine.script_event_floats;
constexpr std::size_t kOffStrings    = L::kEngine.script_event_strings;
constexpr std::size_t kOffObjects    = L::kEngine.script_event_objects;
constexpr std::size_t kObjectBytes   = L::kEngine.object_id_bytes;

// CGameObject.id: +4 on i386, +8 (64-bit) on x86_64. CSWSArea embeds the
// CGameObject subobject at +284 / +0x158. CSWSModule holds it through a
// pointer at +28 on i386 (medium confidence) and embeds it at +0x28 on x86_64
// (RTTI offset-to-top of its CGameObject vtable).
constexpr std::size_t kIdOffset         = L::kEngine.game_object_id;
constexpr std::size_t kAreaGameObject   = L::kEngine.area_game_object;
constexpr std::size_t kModuleGameObject = L::kEngine.module_game_object;
constexpr bool        kModuleIsPointer  = L::kEngine.module_game_object_is_pointer;

struct ExoString {
    const char*   c_string;
    std::uint32_t length;
};
static_assert(sizeof(ExoString) == (sizeof(void*) == 8 ? 16 : 8), "CExoString width");

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

// An object id as the engine stores it (4 or 8 bytes), as the 32-bit value
// scripts see. Little-endian, so the low half is the first four bytes either
// way; the width only matters for the readability probe and the stride.
std::uint32_t read_object_id(const void* p, std::size_t off) {
    const auto* base = static_cast<const std::uint8_t*>(p);
    if (!readable(base + off, kObjectBytes)) return kObjectInvalid;
    abi::ObjectId v = 0;
    std::memcpy(&v, base + off, sizeof v);
    return abi::script_id(v);
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
    static_assert(sizeof(abi::ObjectId) == kObjectBytes, "object list element width");
    return abi::script_id(slot_or<abi::ObjectId>(ev, kOffObjects, index, abi::ObjectId(kObjectInvalid)));
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
        return read_object_id(self, kAreaGameObject + kIdOffset);
    if (hook_site == "event.module") {
        if (!kModuleIsPointer) return read_object_id(self, kModuleGameObject + kIdOffset);
        if (void* go = read_ptr(self, kModuleGameObject))
            return read_object_id(go, kIdOffset);
        return kObjectInvalid;
    }
    return read_object_id(self, kIdOffset);
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
