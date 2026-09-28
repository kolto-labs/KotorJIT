// A small JSON value, reader and writer for the harness wire protocol.
//
// The protocol needs six value types and nothing else: null, boolean, number,
// string, array, object. A general-purpose library would bring a parser far
// larger than the thing it serves, and this code is compiled into a DLL that
// runs inside a game -- every dependency is a dependency the player carries.
//
// Numbers are doubles. Every number the protocol sends fits: object ids are
// unsigned 32-bit, ticks and sequence numbers stay well under 2^53. Integral
// doubles print as integers so the driver sees `4471`, never `4471.0`.
//
// Object keys keep insertion order. That costs nothing and makes replies read
// the way the command wrote them.
#pragma once

#include <cstdint>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace kp::harness {

class Json {
public:
    enum class Type { Null, Bool, Number, String, Array, Object };

    Json() = default;

    static Json null() { return Json(); }
    static Json boolean(bool v);
    static Json number(double v);
    static Json integer(std::int64_t v) { return number(static_cast<double>(v)); }
    static Json unsigned_(std::uint64_t v) { return number(static_cast<double>(v)); }
    static Json string(std::string v);
    static Json array();
    static Json object();

    Type type() const { return type_; }
    bool is_null() const { return type_ == Type::Null; }
    bool is_bool() const { return type_ == Type::Bool; }
    bool is_number() const { return type_ == Type::Number; }
    bool is_string() const { return type_ == Type::String; }
    bool is_array() const { return type_ == Type::Array; }
    bool is_object() const { return type_ == Type::Object; }

    // Typed reads with a default for the wrong type. A request missing a field
    // is the common case in a hand-typed protocol and should not be a crash.
    bool          as_bool(bool fallback = false) const;
    double        as_number(double fallback = 0.0) const;
    std::int64_t  as_int(std::int64_t fallback = 0) const;
    const std::string& as_string() const;   // empty string for a non-string

    // Object access. get() returns null for a missing key or a non-object.
    const Json* get(std::string_view key) const;
    Json&       set(std::string key, Json value);    // replaces an existing key
    bool        has(std::string_view key) const { return get(key) != nullptr; }

    // Array access.
    Json& push(Json value);

    const std::vector<Json>& elements() const { return elements_; }
    const std::vector<std::pair<std::string, Json>>& members() const { return members_; }
    std::size_t size() const;

    // One line, no trailing newline, ASCII-safe: control characters are
    // escaped and everything else passes through as UTF-8.
    std::string dump() const;
    void dump_to(std::string& out) const;

    // Strict JSON, one value, trailing whitespace allowed. `error` names the
    // byte offset and what was expected.
    static bool parse(std::string_view text, Json& out, std::string& error);

private:
    Type        type_ = Type::Null;
    bool        bool_ = false;
    double      number_ = 0.0;
    std::string string_;
    std::vector<Json> elements_;
    std::vector<std::pair<std::string, Json>> members_;
};

// Append `s` to `out` as a quoted JSON string.
void json_escape(std::string_view s, std::string& out);

}  // namespace kp::harness
