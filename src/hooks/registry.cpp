#include "hooks/registry.hpp"

#include <cerrno>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <utility>
#include <unordered_set>

#include "api/memory.hpp"
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

    // JValue is self-referential through std::vector<std::pair<std::string,
    // JValue>>. std::vector alone tolerates an incomplete element type, but
    // std::pair's constructors are SFINAE-conditioned on
    // is_implicitly_default_constructible<JValue>, which needs JValue
    // complete to answer -- and an implicitly-generated destructor is
    // synthesized (needing that answer) at the point the class finishes, not
    // lazily. GCC's libstdc++ tolerates the ordering here; Clang does not.
    // Declaring these five out-of-line (defaulted after the closing brace,
    // where JValue is unambiguously complete) defers their generation to
    // that point instead. member() had the same problem for the same
    // reason and gets the same fix.
    JValue();
    JValue(const JValue&);
    JValue(JValue&&) noexcept;
    JValue& operator=(const JValue&);
    JValue& operator=(JValue&&) noexcept;
    ~JValue();

    const JValue* member(std::string_view key) const;
};

JValue::JValue() = default;
JValue::JValue(const JValue&) = default;
JValue::JValue(JValue&&) noexcept = default;
JValue& JValue::operator=(const JValue&) = default;
JValue& JValue::operator=(JValue&&) noexcept = default;
JValue::~JValue() = default;

const JValue* JValue::member(std::string_view key) const {
    if (type != JType::Object) return nullptr;
    for (const auto& kv : object) {
        if (kv.first == key) return &kv.second;
    }
    return nullptr;
}

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

bool parse_hex_bytes(std::string_view hex, std::vector<std::uint8_t>& out) {
    out.clear();
    for (std::size_t i = 0; i + 1 < hex.size(); i += 2) {
        auto nib = [](char ch) -> int {
            if (ch >= '0' && ch <= '9') return ch - '0';
            if (ch >= 'a' && ch <= 'f') return ch - 'a' + 10;
            if (ch >= 'A' && ch <= 'F') return ch - 'A' + 10;
            return -1;
        };
        const int hi = nib(hex[i]), lo = nib(hex[i + 1]);
        if (hi < 0 || lo < 0) { out.clear(); return false; }
        out.push_back(static_cast<std::uint8_t>((hi << 4) | lo));
    }
    return true;
}

bool read_file_text(const std::string& path, std::string& text, std::string& error) {
    std::FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) {
        error = "cannot open " + path + ": " + std::strerror(errno);
        return false;
    }
    text.clear();
    char buf[4096];
    std::size_t n;
    while ((n = std::fread(buf, 1, sizeof(buf), f)) > 0) text.append(buf, n);
    std::fclose(f);
    return true;
}

const JValue* pick_instance(const JValue& entry, const std::string& slug) {
    const JValue* inst = entry.member("instances");
    if (!inst || inst->type != JType::Array || inst->array.empty()) return nullptr;
    if (!slug.empty()) {
        for (const auto& row : inst->array) {
            if (as_string(row.member("binary")) == slug) return &row;
        }
        return nullptr;
    }
    return &inst->array[0];
}

}  // namespace

// ---------------------------------------------------------------------------
// AddressTable
// ---------------------------------------------------------------------------

SiteKind site_kind_from_string(std::string_view s) {
    if (s == "detour")    return SiteKind::Detour;
    if (s == "reference") return SiteKind::Reference;
    if (s == "call")      return SiteKind::Call;
    if (s == "field")     return SiteKind::Field;
    return SiteKind::Unknown;
}

const char* to_string(SiteKind k) {
    switch (k) {
        case SiteKind::Detour:    return "detour";
        case SiteKind::Reference: return "reference";
        case SiteKind::Call:      return "call";
        case SiteKind::Field:     return "field";
        case SiteKind::Unknown:   return "unknown";
    }
    return "?";
}

namespace {

// `offset` and `size` for a field site. Both live on the entry the generator
// wrote (per-build table) or on the picked instance (hook pack), so this reads
// from whichever object the caller hands it. A Field with a size counts as
// resolved even at addr 0: the address is a chain the adapter walks, and the
// offset is the whole binding.
void parse_field_extent(const JValue& obj, Site& s) {
    if (const JValue* o = obj.member("offset"); o && o->type == JType::Number) {
        s.offset = static_cast<std::uint32_t>(o->number);
    }
    if (const JValue* z = obj.member("size"); z && z->type == JType::Number) {
        s.size = static_cast<std::uint32_t>(z->number);
    }
    if (s.kind == SiteKind::Field && s.size != 0) s.resolved = true;
}

}  // namespace

bool AddressTable::parse(std::string_view json, AddressTable& out, std::string& error) {
    return parse(json, std::string(), out, error);
}

bool AddressTable::parse(std::string_view json, const std::string& build_slug,
                         AddressTable& out, std::string& error) {
    JValue root;
    if (!JParser(json).parse(root, error)) return false;
    if (root.type != JType::Object) {
        error = "address table is not a JSON object";
        return false;
    }

    if (as_string(root.member("format")) == "agentdecompile.hookpack/v1") {
        out = AddressTable{};
        out.build_ = !build_slug.empty() ? build_slug : as_string(root.member("build"));
        bool declared_binaries = false;
        bool selected_binary = false;
        if (const JValue* bins = root.member("binaries"); bins && bins->type == JType::Array) {
            declared_binaries = true;
            for (const auto& b : bins->array) {
                if (b.type != JType::Object) continue;
                const std::string slug = as_string(b.member("slug"));
                if (!out.build_.empty() && slug != out.build_) continue;
                out.game_ = as_string(b.member("game"));
                out.platform_ = as_string(b.member("platform"));
                if (const JValue* ib = b.member("image_base"); ib && ib->type == JType::Number) {
                    out.image_base_ = static_cast<std::uintptr_t>(ib->number);
                }
                out.sha256_ = as_string(b.member("sha256"));
                if (out.build_.empty()) out.build_ = slug;
                selected_binary = true;
                break;
            }
        }
        if (!build_slug.empty() && declared_binaries && !selected_binary) {
            error = "hookpack has no binary entry for selected build " + build_slug;
            return false;
        }
        const JValue* sites = root.member("sites");
        if (!sites || sites->type != JType::Object) {
            error = "hookpack has no \"sites\" object";
            return false;
        }
        for (const auto& [name, entry] : sites->object) {
            if (entry.type != JType::Object) continue;
            Site s;
            s.name     = name;
            s.adapter_key = as_string(entry.member("adapter_key"));
            if (const JValue* aliases = entry.member("aliases"); aliases && aliases->type == JType::Array) {
                for (const JValue& alias : aliases->array) {
                    if (alias.type == JType::String && !alias.str.empty()) s.aliases.push_back(alias.str);
                }
            }
            s.cls      = as_string(entry.member("cls"));
            s.method   = as_string(entry.member("method"));
            s.kind     = site_kind_from_string(as_string(entry.member("kind")));
            s.required = as_bool(entry.member("required"));
            if (const JValue* e = entry.member("expected_bytes"); e && e->type == JType::String) {
                parse_hex_bytes(e->str, s.expected);
            }
            parse_field_extent(entry, s);
            if (const JValue* picked = pick_instance(entry, out.build_)) {
                if (const JValue* a = picked->member("addr"); a && a->type == JType::Number) {
                    s.addr = static_cast<std::uintptr_t>(a->number);
                    s.resolved = s.addr != 0;
                }
                if (const JValue* e = picked->member("expected_bytes"); e && e->type == JType::String) {
                    parse_hex_bytes(e->str, s.expected);
                }
                if (s.cls.empty()) s.cls = as_string(picked->member("cls"));
                if (s.method.empty()) s.method = as_string(picked->member("method"));
                if (const JValue* c = picked->member("confidence"); c && c->type == JType::Number) {
                    s.confidence = c->number;
                }
                parse_field_extent(*picked, s);
            }
            if (const JValue* c = entry.member("confidence"); c && c->type == JType::Number) {
                s.confidence = c->number;
            }
            out.sites_.push_back(std::move(s));
        }
        if (const JValue* operations = root.member("operations"); operations && operations->type == JType::Array) {
            for (const JValue& operation : operations->array) {
                if (operation.type != JType::Object) continue;
                const std::string id = as_string(operation.member("id"));
                const JValue* target = operation.member("target");
                const JValue* roles = operation.member("roles");
                if (id.empty() || !target || target->type != JType::Object || !roles || roles->type != JType::Object)
                    continue;
                if (as_string(target->member("slug")) != out.build_ ||
                    out.sha256_.empty() || as_string(target->member("sha256")) != out.sha256_)
                    continue;
                bool valid = !roles->object.empty();
                for (const auto& [role, declaration] : roles->object) {
                    (void)role;
                    if (declaration.type != JType::Object) { valid = false; break; }
                    const std::string site_name = as_string(declaration.member("site"));
                    const std::string adapter_key = as_string(declaration.member("adapter_key"));
                    const JValue* address = declaration.member("addr");
                    const std::string expected = as_string(declaration.member("expected_bytes"));
                    const Site* site = out.find_adapter(adapter_key);
                    if (site == nullptr || site->name != site_name || !address || address->type != JType::Number ||
                        site->addr != static_cast<std::uintptr_t>(address->number) || expected.empty()) {
                        valid = false;
                        break;
                    }
                    std::vector<std::uint8_t> bytes;
                    if (!parse_hex_bytes(expected, bytes) || bytes.empty() || bytes != site->expected) {
                        valid = false;
                        break;
                    }
                }
                if (valid) out.operations_.push_back(id);
            }
            std::sort(out.operations_.begin(), out.operations_.end());
            out.operations_.erase(std::unique(out.operations_.begin(), out.operations_.end()), out.operations_.end());
        }
        return true;
    }

    out = AddressTable{};
    out.build_    = !build_slug.empty() ? build_slug : as_string(root.member("build"));
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
            parse_hex_bytes(e->str, s.expected);
        }
        if (const JValue* c = entry.member("confidence"); c && c->type == JType::Number) {
            s.confidence = c->number;
        }
        parse_field_extent(entry, s);
        out.sites_.push_back(std::move(s));
    }
    return true;
}

bool AddressTable::load_file(const std::string& path, AddressTable& out, std::string& error) {
    std::string text;
    if (!read_file_text(path, text, error)) return false;
    if (!parse(text, out, error)) {
        error = path + ": " + error;
        return false;
    }
    return true;
}

bool AddressTable::load_hookpack(const std::string& pack_path,
                                 const std::string& build_slug,
                                 const std::string& overlay_path,
                                 AddressTable& out,
                                 std::string& error) {
    std::string text;
    if (!read_file_text(pack_path, text, error)) return false;
    if (!parse(text, build_slug, out, error)) {
        error = pack_path + ": " + error;
        return false;
    }
    if (overlay_path.empty()) return true;
    AddressTable overlay;
    if (!load_file(overlay_path, overlay, error)) return false;
    out.merge_overlay(overlay);
    return true;
}

void AddressTable::merge_overlay(const AddressTable& overlay) {
    for (Site& s : sites_) {
        const Site* o = overlay.find(s.name);
        if (o == nullptr) continue;
        if (!o->expected.empty()) s.expected = o->expected;
        if (o->kind != SiteKind::Unknown) s.kind = o->kind;
        if (o->required) s.required = true;
        if (s.addr == 0 && o->addr != 0) {
            s.addr = o->addr;
            s.resolved = true;
        }
        if (s.cls.empty()) s.cls = o->cls;
        if (s.method.empty()) s.method = o->method;
        if (s.confidence == 0.0 && o->confidence != 0.0) s.confidence = o->confidence;
        if (s.size == 0 && o->size != 0) {
            s.offset = o->offset;
            s.size = o->size;
            if (s.kind == SiteKind::Field) s.resolved = true;
        }
    }
    for (const Site& o : overlay.sites()) {
        if (find(o.name) == nullptr) sites_.push_back(o);
    }
    if (image_base_ == 0) image_base_ = overlay.image_base();
    if (sha256_.empty()) sha256_ = overlay.expected_sha256();
    if (game_.empty()) game_ = overlay.game();
    if (platform_.empty()) platform_ = overlay.platform_name();
}

const Site* AddressTable::find(std::string_view name) const {
    for (const Site& s : sites_) {
        if (s.name == name) return &s;
    }
    return nullptr;
}

const Site* AddressTable::find_adapter(std::string_view adapter_key) const {
    const Site* matched = nullptr;
    for (const Site& s : sites_) {
        const bool exact = s.adapter_key == adapter_key;
        const bool alias = std::find(s.aliases.begin(), s.aliases.end(), adapter_key) != s.aliases.end();
        if (!exact && !alias) continue;
        if (matched != nullptr) return nullptr;
        matched = &s;
    }
    return matched;
}

bool AddressTable::has_operation(std::string_view operation_id) const {
    return std::binary_search(operations_.begin(), operations_.end(), std::string(operation_id));
}

void AddressTable::resolve_from_signatures(std::uintptr_t runtime_base) {
    const std::uintptr_t live = (runtime_base == 0) ? image_base_ : runtime_base;
    const std::intptr_t delta = static_cast<std::intptr_t>(live - image_base_);

    for (Site& s : sites_) {
        s.bound_from_scan = false;
        // A field has no bytes of its own; its resolution is the offset it
        // carries. Scanning would only ever clear it.
        if (s.kind == SiteKind::Field) continue;
        if (s.expected.empty()) continue;

        const std::uintptr_t hint = (s.addr == 0) ? 0
            : static_cast<std::uintptr_t>(static_cast<std::intptr_t>(s.addr) + delta);
        if (hint != 0 &&
            platform::is_readable(reinterpret_cast<const void*>(hint), s.expected.size()) &&
            std::memcmp(reinterpret_cast<const void*>(hint), s.expected.data(), s.expected.size()) == 0) {
            s.resolved = true;
            continue;
        }

        const std::uintptr_t hit = api::memory::find_unique(s.expected.data(), s.expected.size());
        if (hit == 0) {
            s.resolved = false;
            continue;
        }
        s.addr = static_cast<std::uintptr_t>(static_cast<std::intptr_t>(hit) - delta);
        s.resolved = s.addr != 0;
        s.bound_from_scan = s.resolved;
    }
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
