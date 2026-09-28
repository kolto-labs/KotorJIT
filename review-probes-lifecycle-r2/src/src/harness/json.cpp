// JSON reader and writer. See json.hpp for what is deliberately left out.
#include "harness/json.hpp"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace kp::harness {

// ------------------------------------------------------------ construction --

Json Json::boolean(bool v) {
    Json j;
    j.type_ = Type::Bool;
    j.bool_ = v;
    return j;
}

Json Json::number(double v) {
    Json j;
    j.type_ = Type::Number;
    j.number_ = v;
    return j;
}

Json Json::string(std::string v) {
    Json j;
    j.type_ = Type::String;
    j.string_ = std::move(v);
    return j;
}

Json Json::array() {
    Json j;
    j.type_ = Type::Array;
    return j;
}

Json Json::object() {
    Json j;
    j.type_ = Type::Object;
    return j;
}

// ------------------------------------------------------------------- reads --

bool Json::as_bool(bool fallback) const {
    return type_ == Type::Bool ? bool_ : fallback;
}

double Json::as_number(double fallback) const {
    return type_ == Type::Number ? number_ : fallback;
}

std::int64_t Json::as_int(std::int64_t fallback) const {
    if (type_ != Type::Number) return fallback;
    if (std::isnan(number_) || std::isinf(number_)) return fallback;
    // A double outside the int64 range is undefined behaviour to convert, and
    // `1e20` is a request a client can send. The bounds are written as doubles
    // that are exactly representable: 2^63 is the first value past the range,
    // and -2^63 is the lowest value in it.
    const double truncated = std::trunc(number_);
    if (!(truncated >= -9223372036854775808.0) || !(truncated < 9223372036854775808.0))
        return fallback;
    return static_cast<std::int64_t>(truncated);
}

const std::string& Json::as_string() const {
    static const std::string empty;
    return type_ == Type::String ? string_ : empty;
}

const Json* Json::get(std::string_view key) const {
    if (type_ != Type::Object) return nullptr;
    for (const auto& m : members_)
        if (m.first == key) return &m.second;
    return nullptr;
}

Json& Json::set(std::string key, Json value) {
    if (type_ != Type::Object) {
        type_ = Type::Object;
        elements_.clear();
        string_.clear();
    }
    for (auto& m : members_) {
        if (m.first == key) {
            m.second = std::move(value);
            return m.second;
        }
    }
    members_.emplace_back(std::move(key), std::move(value));
    return members_.back().second;
}

Json& Json::push(Json value) {
    if (type_ != Type::Array) {
        type_ = Type::Array;
        members_.clear();
        string_.clear();
    }
    elements_.push_back(std::move(value));
    return elements_.back();
}

std::size_t Json::size() const {
    switch (type_) {
    case Type::Array:  return elements_.size();
    case Type::Object: return members_.size();
    case Type::String: return string_.size();
    default:           return 0;
    }
}

// ------------------------------------------------------------------- write --

void json_escape(std::string_view s, std::string& out) {
    out.push_back('"');
    for (const char ch : s) {
        const auto c = static_cast<unsigned char>(ch);
        switch (c) {
        case '"':  out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        case '\b': out += "\\b"; break;
        case '\f': out += "\\f"; break;
        default:
            if (c < 0x20) {
                char buf[8];
                std::snprintf(buf, sizeof buf, "\\u%04x", c);
                out += buf;
            } else {
                out.push_back(ch);
            }
        }
    }
    out.push_back('"');
}

namespace {

void dump_number(double v, std::string& out) {
    // NaN and infinity have no JSON spelling. null is the one honest answer.
    if (std::isnan(v) || std::isinf(v)) { out += "null"; return; }
    char buf[32];
    const double r = std::floor(v);
    if (r == v && std::fabs(v) < 9007199254740992.0) {
        std::snprintf(buf, sizeof buf, "%lld", static_cast<long long>(v));
    } else {
        std::snprintf(buf, sizeof buf, "%.17g", v);
    }
    out += buf;
}

}  // namespace

void Json::dump_to(std::string& out) const {
    switch (type_) {
    case Type::Null:   out += "null"; break;
    case Type::Bool:   out += bool_ ? "true" : "false"; break;
    case Type::Number: dump_number(number_, out); break;
    case Type::String: json_escape(string_, out); break;
    case Type::Array:
        out.push_back('[');
        for (std::size_t i = 0; i < elements_.size(); ++i) {
            if (i != 0) out.push_back(',');
            elements_[i].dump_to(out);
        }
        out.push_back(']');
        break;
    case Type::Object:
        out.push_back('{');
        for (std::size_t i = 0; i < members_.size(); ++i) {
            if (i != 0) out.push_back(',');
            json_escape(members_[i].first, out);
            out.push_back(':');
            members_[i].second.dump_to(out);
        }
        out.push_back('}');
        break;
    }
}

std::string Json::dump() const {
    std::string out;
    dump_to(out);
    return out;
}

// -------------------------------------------------------------------- read --

namespace {

// Nesting past this is not a request anyone typed; it is either a bug or an
// attempt to blow the stack, and the answer to both is a parse error.
constexpr int kMaxDepth = 64;

struct Parser {
    std::string_view text;
    std::size_t      at = 0;
    std::string      error;

    bool fail(const char* what) {
        if (error.empty()) {
            char buf[96];
            std::snprintf(buf, sizeof buf, "json: %s at offset %zu", what, at);
            error = buf;
        }
        return false;
    }

    void skip_ws() {
        while (at < text.size()) {
            const char c = text[at];
            if (c == ' ' || c == '\t' || c == '\n' || c == '\r') ++at;
            else break;
        }
    }

    bool peek(char c) const { return at < text.size() && text[at] == c; }

    bool expect_literal(const char* lit, std::size_t n) {
        if (text.size() - at < n || text.compare(at, n, lit) != 0) return fail("bad literal");
        at += n;
        return true;
    }

    static void append_utf8(std::uint32_t cp, std::string& out) {
        if (cp < 0x80) {
            out.push_back(static_cast<char>(cp));
        } else if (cp < 0x800) {
            out.push_back(static_cast<char>(0xC0 | (cp >> 6)));
            out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
        } else if (cp < 0x10000) {
            out.push_back(static_cast<char>(0xE0 | (cp >> 12)));
            out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
        } else {
            out.push_back(static_cast<char>(0xF0 | (cp >> 18)));
            out.push_back(static_cast<char>(0x80 | ((cp >> 12) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | ((cp >> 6) & 0x3F)));
            out.push_back(static_cast<char>(0x80 | (cp & 0x3F)));
        }
    }

    bool hex4(std::uint32_t& out) {
        if (text.size() - at < 4) return fail("short \\u escape");
        out = 0;
        for (int i = 0; i < 4; ++i) {
            const char c = text[at++];
            out <<= 4;
            if (c >= '0' && c <= '9')      out |= static_cast<std::uint32_t>(c - '0');
            else if (c >= 'a' && c <= 'f') out |= static_cast<std::uint32_t>(c - 'a' + 10);
            else if (c >= 'A' && c <= 'F') out |= static_cast<std::uint32_t>(c - 'A' + 10);
            else return fail("bad hex digit in \\u escape");
        }
        return true;
    }

    bool parse_string(std::string& out) {
        if (!peek('"')) return fail("expected string");
        ++at;
        while (true) {
            if (at >= text.size()) return fail("unterminated string");
            const char c = text[at++];
            if (c == '"') return true;
            if (static_cast<unsigned char>(c) < 0x20) return fail("control character in string");
            if (c != '\\') { out.push_back(c); continue; }
            if (at >= text.size()) return fail("unterminated escape");
            const char e = text[at++];
            switch (e) {
            case '"':  out.push_back('"'); break;
            case '\\': out.push_back('\\'); break;
            case '/':  out.push_back('/'); break;
            case 'b':  out.push_back('\b'); break;
            case 'f':  out.push_back('\f'); break;
            case 'n':  out.push_back('\n'); break;
            case 'r':  out.push_back('\r'); break;
            case 't':  out.push_back('\t'); break;
            case 'u': {
                std::uint32_t cp = 0;
                if (!hex4(cp)) return false;
                if (cp >= 0xD800 && cp <= 0xDBFF) {
                    // High surrogate: the low half must follow as another \u.
                    if (text.size() - at < 6 || text[at] != '\\' || text[at + 1] != 'u')
                        return fail("lone high surrogate");
                    at += 2;
                    std::uint32_t lo = 0;
                    if (!hex4(lo)) return false;
                    if (lo < 0xDC00 || lo > 0xDFFF) return fail("bad low surrogate");
                    cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
                } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
                    return fail("lone low surrogate");
                }
                append_utf8(cp, out);
                break;
            }
            default:
                return fail("bad escape");
            }
        }
    }

    bool parse_number(Json& out) {
        const std::size_t start = at;
        if (peek('-')) ++at;
        if (at >= text.size()) return fail("bad number");
        if (text[at] == '0') {
            ++at;
        } else if (text[at] >= '1' && text[at] <= '9') {
            while (at < text.size() && text[at] >= '0' && text[at] <= '9') ++at;
        } else {
            return fail("bad number");
        }
        if (peek('.')) {
            ++at;
            if (at >= text.size() || text[at] < '0' || text[at] > '9') return fail("bad fraction");
            while (at < text.size() && text[at] >= '0' && text[at] <= '9') ++at;
        }
        if (peek('e') || peek('E')) {
            ++at;
            if (peek('+') || peek('-')) ++at;
            if (at >= text.size() || text[at] < '0' || text[at] > '9') return fail("bad exponent");
            while (at < text.size() && text[at] >= '0' && text[at] <= '9') ++at;
        }
        // strtod wants a terminated buffer; the slice is short by construction.
        const std::string slice(text.substr(start, at - start));
        out = Json::number(std::strtod(slice.c_str(), nullptr));
        return true;
    }

    bool parse_value(Json& out, int depth) {
        if (depth > kMaxDepth) return fail("nested too deeply");
        skip_ws();
        if (at >= text.size()) return fail("unexpected end");
        const char c = text[at];
        switch (c) {
        case 'n': if (!expect_literal("null", 4)) return false; out = Json::null(); return true;
        case 't': if (!expect_literal("true", 4)) return false; out = Json::boolean(true); return true;
        case 'f': if (!expect_literal("false", 5)) return false; out = Json::boolean(false); return true;
        case '"': {
            std::string s;
            if (!parse_string(s)) return false;
            out = Json::string(std::move(s));
            return true;
        }
        case '[': {
            ++at;
            out = Json::array();
            skip_ws();
            if (peek(']')) { ++at; return true; }
            while (true) {
                Json item;
                if (!parse_value(item, depth + 1)) return false;
                out.push(std::move(item));
                skip_ws();
                if (peek(',')) { ++at; continue; }
                if (peek(']')) { ++at; return true; }
                return fail("expected ',' or ']'");
            }
        }
        case '{': {
            ++at;
            out = Json::object();
            skip_ws();
            if (peek('}')) { ++at; return true; }
            while (true) {
                skip_ws();
                std::string key;
                if (!parse_string(key)) return false;
                skip_ws();
                if (!peek(':')) return fail("expected ':'");
                ++at;
                Json value;
                if (!parse_value(value, depth + 1)) return false;
                out.set(std::move(key), std::move(value));
                skip_ws();
                if (peek(',')) { ++at; continue; }
                if (peek('}')) { ++at; return true; }
                return fail("expected ',' or '}'");
            }
        }
        default:
            if (c == '-' || (c >= '0' && c <= '9')) return parse_number(out);
            return fail("unexpected character");
        }
    }
};

}  // namespace

bool Json::parse(std::string_view text, Json& out, std::string& error) {
    Parser p;
    p.text = text;
    Json value;
    if (!p.parse_value(value, 0)) { error = p.error; return false; }
    p.skip_ws();
    if (p.at != text.size()) { p.fail("trailing characters"); error = p.error; return false; }
    out = std::move(value);
    return true;
}

}  // namespace kp::harness
