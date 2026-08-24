// Moving values across the Lua boundary.
//
// The conversion rules here are not incidental -- they decide whether a script
// is understood to have answered an event or to have abstained from it, so they
// are written out explicitly rather than left to whatever lua_toboolean happens
// to do.
#pragma once

#include <cstdint>
#include <string>
#include <variant>

#include "events/contract.hpp"

struct lua_State;

namespace kp::lua {

// One value crossing the boundary in either direction.
class Value {
public:
    using Storage = std::variant<std::monostate, bool, std::int64_t, double,
                                 std::string, std::uint32_t>;

    Value() = default;
    static Value none()                     { return Value{Storage{std::monostate{}}}; }
    static Value boolean(bool v)            { return Value{Storage{v}}; }
    static Value integer(std::int64_t v)    { return Value{Storage{v}}; }
    static Value number(double v)           { return Value{Storage{v}}; }
    static Value str(std::string v)         { return Value{Storage{std::move(v)}}; }
    static Value object(std::uint32_t v)    { return Value{Storage{v}}; }

    bool is_none() const { return std::holds_alternative<std::monostate>(v_); }
    const Storage& storage() const { return v_; }

    void push(lua_State*) const;

private:
    explicit Value(Storage v) : v_(std::move(v)) {}
    Storage v_;
};

// Why a conversion failed. Anything other than Ok means the script abstained
// from this event rather than answering it.
enum class ConvertResult { Ok, WrongType, NoValue };

// Read one result off the Lua stack at `index` as `want`.
//
// The rules, stated so they cannot quietly change:
//
//   nil or no value        -> NoValue.        The script abstained.
//   a number, for Int/     -> Ok.
//     Float/Bool
//   a string, for a number -> Ok if the WHOLE string parses as a number, so
//                             "5" converts and "5x" does not. Trailing garbage
//                             is a failure, not a truncation.
//   any other string       -> WrongType. Abstained.
//   for Bool               -> the value is compared against 1. A script
//                             returning 2 yields false, not true. That is
//                             deliberate: it matches the model we implement,
//                             and silently widening it would change which
//                             scripts win an event.
//   a boolean, for Int     -> Ok, as 0 or 1.
//
// `out` is only written when Ok is returned.
ConvertResult convert(lua_State*, int index, events::ValueType want, Value& out);

// Read a whole result tuple. All-or-nothing on purpose: if any slot fails, the
// script abstained entirely. A script that answers the first of three results
// and fumbles the second has not answered the event, and treating it as a
// partial answer would let it beat a later script that answered properly.
bool convert_tuple(lua_State*, int first_index,
                   const std::vector<events::ValueType>& want,
                   std::vector<Value>& out);

}  // namespace kp::lua
