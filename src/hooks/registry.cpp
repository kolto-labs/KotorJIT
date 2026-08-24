#include "hooks/registry.hpp"

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <utility>

#include "platform/platform.hpp"

namespace kp::hooks {
namespace {

// ---------------------------------------------------------------------------
// A JSON reader, deliberately small
//
// The runtime ships as an injected DLL into a game that predates every JSON
// library, and pulling one in would put a third-party allocator and a third-party
// exception path inside the game's process for the sake of reading one config
// file. The generator's output is machine-written, so this reads the whole of
// RFC 8259's grammar minus the parts that output never contains: no \u escapes
// beyond passing them through, and numbers land in a double, which is exact for
// every address in a 32-bit space.
// ---------------------------------------------------------------------------

enum class JType { Null, Bool, Number, String, Array, Object };

struct JValue {
    JType type = JType::Null;
    bool  boolean = false;
    double number = 0.0;
    std::string str;
    std::vector<JValue> array;
    std::vector<std::pair<std::string, JValue>> object;

    const JValue* member(std::string_view key) const {
        if (type != JType::Object) return nullptr;
        for (const auto& [k, v] : object) {
            if (k == key) return &v;
        }
        return nullptr;
    }
};

class JParser {
public:
    JParser(std::string_view text) : s_(text) {}

    bool parse(JValue& out, std::string& error) {
        skip_ws();
        if (!value(out, error)) return false;
        skip_ws();
        if (i_ != s_.size()) {
            error = fail("trailing content after the top-level value");
            return false;
        }
        return true;
    }

private:
    std::string_view s_;
    std::size_t i_ = 0;

    std::string fail(const char* what) const {
        char buf[160];
        std::snprintf(buf, sizeof(buf), "%s at byte %zu", what, i_);
        return buf;
    }

    void skip_ws() {
        while (i_ < s_.size()) {
            const char c = s_[i_];
            if (c == ' ' || c == '\t' || c == '\n' || c == '\r') ++i_;
            else break;
        }
    }

    bool literal(std::string_view lit) {
        if (s_.compare(i_, lit.size(), lit) != 0) return false;
        i_ += lit.size();
        return true;
    }

    bool value(JValue& out, std::string& error) {
        if (i_ >= s_.size()) { error = fail("unexpected end of input"); return false; }
        switch (s_[i_]) {
            case '{': return object(out, error);
            case '[': return array(out, error);
            case '"': out.type = JType::String; return string(out.str, error);
            case 't':
                if (!literal("true")) { error = fail("bad literal"); return false; }
                out.type = JType::Bool; out.boolean = true; return true;
            case 'f':
                if (!literal("false")) { error = fail("bad literal"); return false; }
                out.type = JType::Bool; out.boolean = false; return true;
            case 'n':
                if (!literal("null")) { error = fail("bad literal"); return false; }
                out.type = JType::Null; return true;
            default: return number(out, error);
        }
    }

    bool object(JValue& out, std::string& error) {
        out.type = JType::Object;
        ++i_;  // '{'
        skip_ws();
        if (i_ < s_.size() && s_[i_] == '}') { ++i_; return true; }
        for (;;) {
            skip_ws();
            std::string key;
            if (i_ >= s_.size() || s_[i_] != '"') { error = fail("expected a member name"); return false; }
            if (!string(key, error)) return false;
            skip_ws();
            if (i_ >= s_.size() || s_[i_] != ':') { error = fail("expected ':'"); return false; }
            ++i_;
            skip_ws();
            JValue v;
            if (!value(v, error)) return false;
            out.object.emplace_back(std::move(key), std::move(v));
            skip_ws();
            if (i_ < s_.size() && s_[i_] == ',') { ++i_; continue; }
            if (i_ < s_.size() && s_[i_] == '}') { ++i_; return true; }
            error = fail("expected ',' or '}'");
            return false;
        }
    }

    bool array(JValue& out, std::string& error) {
        out.type = JType::Array;
        ++i_;  // '['
        skip_ws();
        if (i_ < s_.size() && s_[i_] == ']') { ++i_; return true; }
        for (;;) {
            skip_ws();
            JValue v;
            if (!value(v, error)) return false;
            out.array.push_back(std::move(v));
            skip_ws();
            if (i_ < s_.size() && s_[i_] == ',') { ++i_; continue; }
            if (i_ < s_.size() && s_[i_] == ']') { ++i_; return true; }
            error = fail("expected ',' or ']'");
            return false;
        }
    }

    bool string(std::string& out, std::string& error) {
        ++i_;  // opening quote
        out.clear();
        while (i_ < s_.size()) {
            const char c = s_[i_++];
            if (c == '"') return true;
            if (c != '\\') { out.push_back(c); continue; }
            if (i_ >= s_.size()) break;
            const char e = s_[i_++];
            switch (e) {
                case '"':  out.push_back('"');  break;
                case '\\': out.push_back('\\'); break;
                case '/':  out.push_back('/');  break;
                case 'b':  out.push_back('\b'); break;
                case 'f':  out.push_back('\f'); break;
                case 'n':  out.push_back('\n'); break;
                case 'r':  out.push_back('\r'); break;
                case 't':  out.push_back('\t'); break;
                case 'u':
                    // Every string in a generated address table is ASCII. Rather
                    // than carry a UTF-16-surrogate decoder that would never run,
                    // the escape is preserved verbatim so nothing is silently lost.
                    out += "\\u";
                    for (int k = 0; k < 4 && i_ < s_.size(); ++k) out.push_back(s_[i_++]);
                    break;
                default:
                    error = fail("unknown escape");
                    return false;
            }
        }
        error = fail("unterminated string");
        return false;
    }

    bool number(JValue& out, std::string& error) {
        const std::size_t start = i_;
        if (i_ < s_.size() && (s_[i_] == '-' || s_[i_] == '+')) ++i_;
        bool any = false;
        while (i_ < s_.size() && s_[i_] >= '0' && s_[i_] <= '9') { ++i_; any = true; }
        if (i_ < s_.size() && s_[i_] == '.') {
            ++i_;
            while (i_ < s_.size() && s_[i_] >= '0' && s_[i_] <= '9') { ++i_; any = true; }
        }
        if (i_ < s_.size() && (s_[i_] == 'e' || s_[i_] == 'E')) {
            ++i_;
            if (i_ < s_.size() && (s_[i_] == '-' || s_[i_] == '+')) ++i_;
            while (i_ < s_.size() && s_[i_] >= '0' && s_[i_] <= '9') ++i_;
        }
        if (!any) { error = fail("expected a value"); return false; }
        out.type = JType::Number;
        out.number = std::strtod(std::string(s_.substr(start, i_ - start)).c_str(), nullptr);
        return true;
    }
};

std::string as_string(const JValue* v) {
    return (v && v->type == JType::String) ? v->str : std::string();
}

bool as_bool(const JValue* v, bool fallback = false) {
    return (v && v->type == JType::Bool) ? v->boolean : fallback;
}

}  // namespace

// ---------------------------------------------------------------------------
// AddressTable
// ---------------------------------------------------------------------------

SiteKind site_kind_from_string(std::string_view s) {
    if (s == "detour")    return SiteKind::Detour;
    if (s == "reference") return SiteKind::Reference;
    if (s == "call")      return SiteKind::Call;
    return SiteKind::Unknown;
}

const char* to_string(SiteKind k) {
    switch (k) {
        case SiteKind::Detour:    return "detour";
        case SiteKind::Reference: return "reference";
        case SiteKind::Call:      return "call";
        case SiteKind::Unknown:   return "unknown";
    }
    return "?";
}

bool AddressTable::parse(std::string_view json, AddressTable& out, std::string& error) {
    JValue root;
    if (!JParser(json).parse(root, error)) return false;
    if (root.type != JType::Object) {
        error = "address table is not a JSON object";
        return false;
    }

    out = AddressTable{};
    out.build_    = as_string(root.member("build"));
    out.game_     = as_string(root.member("game"));
    out.platform_ = as_string(root.member("platform"));

    if (const JValue* ib = root.member("image_base"); ib && ib->type == JType::Number) {
        out.image_base_ = static_cast<std::uintptr_t>(ib->number);
    }
    if (const JValue* id = root.member("identity")) {
        out.sha256_ = as_string(id->member("sha256"));
    }

    const JValue* sites = root.member("sites");
    if (!sites || sites->type != JType::Object) {
        error = "address table has no \"sites\" object";
        return false;
    }

    for (const auto& [name, entry] : sites->object) {
        if (entry.type != JType::Object) continue;
        Site s;
        s.name     = name;
        s.cls      = as_string(entry.member("cls"));
        s.method   = as_string(entry.member("method"));
        s.kind     = site_kind_from_string(as_string(entry.member("kind")));
        s.required = as_bool(entry.member("required"));

        // The generator writes `addr` as an absolute VA already biased by
        // image_base -- 6112720 is 0x5D45D0, not an offset from 0x400000.
        // Adding image_base here would double-count it.
        if (const JValue* a = entry.member("addr"); a && a->type == JType::Number) {
            s.addr = static_cast<std::uintptr_t>(a->number);
            s.resolved = s.addr != 0;
        }
        if (const JValue* e = entry.member("expected_bytes"); e && e->type == JType::String) {
            const std::string& hex = e->str;
            for (std::size_t i = 0; i + 1 < hex.size(); i += 2) {
                auto nib = [](char ch) -> int {
                    if (ch >= '0' && ch <= '9') return ch - '0';
                    if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
                    if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
                    return -1;
                };
                const int hi = nib(hex[i]), lo = nib(hex[i + 1]);
                if (hi < 0 || lo < 0) { s.expected.clear(); break; }
                s.expected.push_back(static_cast<std::uint8_t>((hi << 4) | lo));
            }
        }
        if (const JValue* c = entry.member("confidence"); c && c->type == JType::Number) {
            s.confidence = c->number;
        }
        out.sites_.push_back(std::move(s));
    }
    return true;
}

bool AddressTable::load_file(const std::string& path, AddressTable& out, std::string& error) {
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) {
        error = "cannot open " + path + ": " + std::strerror(errno);
        return false;
    }
    std::string text;
    char buf[4096];
    std::size_t n;
    while ((n = std::fread(buf, 1, sizeof(buf), f)) > 0) text.append(buf, n);
    std::fclose(f);
    if (!parse(text, out, error)) {
        error = path + ": " + error;
        return false;
    }
    return true;
}

const Site* AddressTable::find(std::string_view name) const {
    for (const Site& s : sites_) {
        if (s.name == name) return &s;
    }
    return nullptr;
}

std::vector<std::string> AddressTable::unresolved_required() const {
    std::vector<std::string> missing;
    for (const Site& s : sites_) {
        // Every kind counts here, not just detours -- see the header. A required
        // `reference` that did not bind is just as fatal as a required detour.
        if (s.required && !s.resolved) missing.push_back(s.name);
    }
    return missing;
}

// ---------------------------------------------------------------------------
// HookSet
// ---------------------------------------------------------------------------

HookSet::~HookSet() {
    uninstall();
}

void HookSet::add(HookRequest r) {
    requests_.push_back(std::move(r));
}

bool HookSet::install(const AddressTable& table, std::uintptr_t runtime_base,
                      std::string& error) {
    if (!installed_.empty()) {
        error = "hook set is already installed";
        return false;
    }

    // --- resolution, across every kind, before anything is written ---------

    const std::vector<std::string> missing = table.unresolved_required();
    if (!missing.empty()) {
        error = "build " + table.build() + " does not resolve required site(s):";
        for (const std::string& m : missing) error += " " + m;
        return false;
    }

    const std::intptr_t delta =
        (runtime_base == 0) ? 0
                            : static_cast<std::intptr_t>(runtime_base - table.image_base());

    struct Resolved {
        const HookRequest* request;
        std::uintptr_t     addr;
        const Site*        site;
    };
    std::vector<Resolved> plan;
    plan.reserve(requests_.size());

    for (const HookRequest& r : requests_) {
        const Site* site = table.find(r.site);
        if (!site) {
            error = "site \"" + r.site + "\" is not in build " + table.build();
            return false;
        }
        if (!site->resolved) {
            error = "site \"" + r.site + "\" is unresolved in build " + table.build();
            return false;
        }
        if (site->kind != SiteKind::Detour) {
            // Refuse rather than skip. A caller that asked to patch a `call` or
            // `reference` site has a bug, and quietly doing nothing would hide
            // it until the feature it expected turned out to be missing.
            error = "site \"" + r.site + "\" is kind=" + to_string(site->kind) +
                    " and cannot be detoured";
            return false;
        }
        if (!r.detour) {
            error = "site \"" + r.site + "\" has no detour function";
            return false;
        }
        plan.push_back({&r, static_cast<std::uintptr_t>(site->addr + delta), site});
    }

    // --- installation, with rollback --------------------------------------

    for (const Resolved& p : plan) {
        auto detour = std::make_unique<Detour>();
        std::string detail;

        // Prefer what the table recorded over what the caller guessed. The
        // generator read the site's prologue straight out of a plaintext
        // reference image, so it is both wider and less likely to be stale
        // than a pattern typed at a call site.
        const std::vector<std::uint8_t>& expect =
            !p.site->expected.empty() ? p.site->expected : p.request->expect;

        const HookStatus st = detour->install(
            reinterpret_cast<void*>(p.addr), p.request->detour,
            expect.empty() ? nullptr : expect.data(), expect.size(), &detail);

        if (st != HookStatus::Ok) {
            error = "site \"" + p.request->site + "\" at 0x";
            char buf[16];
            std::snprintf(buf, sizeof(buf), "%08X", static_cast<unsigned>(p.addr));
            error += buf;
            error += ": ";
            error += to_string(st);
            if (!detail.empty()) error += " (" + detail + ")";
            uninstall();  // roll back whatever already went in
            return false;
        }

        installed_.push_back({p.request->site, std::move(detour)});
    }

    platform::log(platform::LogLevel::Info, "installed %zu hook(s) for build %s",
                  installed_.size(), table.build().c_str());
    return true;
}

void HookSet::uninstall() {
    // Reverse order. Nothing in the engine requires it today, but if two sites
    // ever overlap, undoing them in the order they went in would restore the
    // wrong bytes.
    for (auto it = installed_.rbegin(); it != installed_.rend(); ++it) {
        if (it->detour) it->detour->uninstall();
    }
    installed_.clear();
}

void* HookSet::original(std::string_view site) const {
    for (const Installed& i : installed_) {
        if (i.name == site) return i.detour->original();
    }
    return nullptr;
}

}  // namespace kp::hooks
