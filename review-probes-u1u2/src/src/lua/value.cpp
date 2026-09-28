#include "lua/value.hpp"

#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <vector>

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace kp::lua {

void Value::push(lua_State* L) const {
    std::visit([L](auto&& v) {
        using T = std::decay_t<decltype(v)>;
        if constexpr (std::is_same_v<T, std::monostate>)          lua_pushnil(L);
        else if constexpr (std::is_same_v<T, bool>)               lua_pushboolean(L, v);
        else if constexpr (std::is_same_v<T, std::int64_t>)       lua_pushnumber(L, double(v));
        else if constexpr (std::is_same_v<T, double>)             lua_pushnumber(L, v);
        else if constexpr (std::is_same_v<T, std::string>)        lua_pushlstring(L, v.data(), v.size());
        // Object ids are pushed as numbers. Lua 5.1 numbers are doubles, which
        // hold every 32-bit value exactly, so no id is lost.
        else if constexpr (std::is_same_v<T, std::uint32_t>)      lua_pushnumber(L, double(v));
    }, v_);
}

namespace {

// Parse a string as a number only if the WHOLE string is one. strtod stopping
// early means trailing garbage, which is a failed conversion rather than a
// value we should salvage.
bool whole_string_to_number(const char* s, std::size_t len, double& out) {
    if (len == 0) return false;
    std::string buf(s, len);
    errno = 0;
    char* end = nullptr;
    const double v = std::strtod(buf.c_str(), &end);
    if (end == buf.c_str() || errno == ERANGE) return false;
    while (*end == ' ' || *end == '\t' || *end == '\n' || *end == '\r') ++end;
    if (*end != '\0') return false;
    out = v;
    return true;
}

// Coerce a stack slot to a number under the string rule above. Booleans count,
// so a script may answer an int-valued event with true/false.
bool slot_as_number(lua_State* L, int idx, double& out) {
    switch (lua_type(L, idx)) {
    case LUA_TNUMBER:
        out = lua_tonumber(L, idx);
        return true;
    case LUA_TBOOLEAN:
        out = lua_toboolean(L, idx) ? 1.0 : 0.0;
        return true;
    case LUA_TSTRING: {
        std::size_t len = 0;
        const char* s = lua_tolstring(L, idx, &len);
        return whole_string_to_number(s, len, out);
    }
    default:
        return false;
    }
}

}  // namespace

ConvertResult convert(lua_State* L, int index, events::ValueType want, Value& out) {
    const int t = lua_type(L, index);
    if (t == LUA_TNONE || t == LUA_TNIL) return ConvertResult::NoValue;

    switch (want) {
    case events::ValueType::None:
        return ConvertResult::Ok;

    case events::ValueType::Bool: {
        double n = 0.0;
        if (!slot_as_number(L, index, n)) return ConvertResult::WrongType;
        // Compared against 1, not tested for truthiness. Returning 2 gives
        // false. See the note in value.hpp -- this is the documented behaviour,
        // not an oversight.
        out = Value::boolean(n == 1.0);
        return ConvertResult::Ok;
    }

    case events::ValueType::Int: {
        double n = 0.0;
        if (!slot_as_number(L, index, n)) return ConvertResult::WrongType;
        // NaN/Inf/out-of-range casts to int64_t are undefined behaviour. -2^63
        // and 2^63 are both exactly representable in a double, so this range
        // check is exact, not an approximation.
        constexpr double kInt64Min = -9223372036854775808.0;
        constexpr double kInt64MaxExclusive = 9223372036854775808.0;
        if (!std::isfinite(n) || n < kInt64Min || n >= kInt64MaxExclusive)
            return ConvertResult::WrongType;
        out = Value::integer(static_cast<std::int64_t>(n));
        return ConvertResult::Ok;
    }

    case events::ValueType::Float: {
        double n = 0.0;
        if (!slot_as_number(L, index, n)) return ConvertResult::WrongType;
        out = Value::number(n);
        return ConvertResult::Ok;
    }

    case events::ValueType::Object: {
        double n = 0.0;
        if (!slot_as_number(L, index, n)) return ConvertResult::WrongType;
        // NaN compares false against everything, including `n < 0.0`, so it
        // slipped past the old guard; !isfinite catches NaN and +-Inf both.
        // Upper bound is UINT32_MAX, matching api/entity.cpp's object_id_at.
        if (!std::isfinite(n) || n < 0.0 || n > 4294967295.0)
            return ConvertResult::WrongType;
        out = Value::object(static_cast<std::uint32_t>(n));
        return ConvertResult::Ok;
    }

    case events::ValueType::String: {
        // Only accept an actual string. lua_tolstring would happily convert a
        // number in place, which mutates the stack slot underneath us and would
        // corrupt a later read of the same value.
        if (t != LUA_TSTRING) return ConvertResult::WrongType;
        std::size_t len = 0;
        const char* s = lua_tolstring(L, index, &len);
        out = Value::str(std::string(s, len));
        return ConvertResult::Ok;
    }
    }
    return ConvertResult::WrongType;
}

bool convert_tuple(lua_State* L, int first_index,
                   const std::vector<events::ValueType>& want,
                   std::vector<Value>& out) {
    // A void event has no results, so there is nothing that can fail and the
    // caller always claims. That is faithful to the model, and it is why every
    // script after the first sees relevant == false on void events.
    if (want.empty()) {
        out.clear();
        return true;
    }

    std::vector<Value> staged;
    staged.reserve(want.size());
    for (std::size_t i = 0; i < want.size(); ++i) {
        Value v;
        if (convert(L, first_index + int(i), want[i], v) != ConvertResult::Ok)
            return false;                 // all-or-nothing; caller abstained
        staged.push_back(std::move(v));
    }
    out = std::move(staged);
    return true;
}

}  // namespace kp::lua
