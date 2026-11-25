#include "hooks/native_call.hpp"

#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <string>
#include <string_view>
#include <vector>

#include "api/memory.hpp"
#include "platform/platform.hpp"

extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace kp::hooks::native {
namespace {

const AddressTable* g_table = nullptr;
std::uintptr_t g_runtime_base = 0;
Guard g_guard = nullptr;

constexpr unsigned kMaxArgs = 8;
const char kBoundFnType[] = "kp.native.fn";

enum class Conv { Cdecl, Stdcall, Thiscall, Sysv };
enum class ValType { Void, I32, U32, F32, Ptr, Cstr, Bool };

struct AbiSpec {
    Conv conv = Conv::Cdecl;
    bool infer_args = false;
    unsigned argc = 0;
    ValType args[kMaxArgs]{};
    ValType ret = ValType::I32;
};

struct BoundFn {
    std::uintptr_t addr = 0;
    AbiSpec abi;
};

struct CallRequest {
    std::uintptr_t addr = 0;
    Conv conv = Conv::Cdecl;
    unsigned argc = 0;
    std::uintptr_t args[kMaxArgs]{};
    ValType ret_type = ValType::Void;
    std::uintptr_t ret_u = 0;
    float ret_f = 0.0f;
};

std::uintptr_t table_delta() {
    if (!g_table || g_runtime_base == 0 || g_table->image_base() == 0) return 0;
    return g_runtime_base - g_table->image_base();
}

int hex_nibble(char c) {
    if (c >= '0' && c <= '9') return c - '0';
    if (c >= 'a' && c <= 'f') return 10 + (c - 'a');
    if (c >= 'A' && c <= 'F') return 10 + (c - 'A');
    return -1;
}

bool parse_pattern_str(std::string_view text, std::vector<std::uint8_t>& val,
                       std::vector<std::uint8_t>& mask) {
    val.clear();
    mask.clear();
    std::vector<char> clean;
    clean.reserve(text.size());
    for (char c : text) {
        if (std::isspace(static_cast<unsigned char>(c))) continue;
        clean.push_back(c);
    }
    if (clean.empty() || (clean.size() % 2) != 0) return false;
    for (std::size_t i = 0; i < clean.size(); i += 2) {
        const char a = clean[i];
        const char b = clean[i + 1];
        if (a == '?' && b == '?') {
            val.push_back(0);
            mask.push_back(0x00);
            continue;
        }
        const int hi = hex_nibble(a);
        const int lo = hex_nibble(b);
        if (hi < 0 || lo < 0) return false;
        val.push_back(static_cast<std::uint8_t>((hi << 4) | lo));
        mask.push_back(0xFF);
    }
    return !val.empty();
}

std::uintptr_t scan_unique_pattern(const std::vector<std::uint8_t>& val,
                                   const std::vector<std::uint8_t>& mask,
                                   std::string& err) {
    if (val.empty() || val.size() != mask.size()) {
        err = "empty or malformed signature pattern";
        return 0;
    }
    if (mask[0] == 0xFF) {
        api::memory::MaskedPattern mp{val.data(), mask.data(), val.size()};
        const auto hits = api::memory::scan_masked({mp});
        if (hits.empty() || hits[0].count == 0) {
            err = "signature not found";
            return 0;
        }
        if (hits[0].count > 1) {
            err = "signature ambiguous (multiple hits)";
            return 0;
        }
        return hits[0].first;
    }
    // Linear scan when byte 0 is wildcarded.
    std::uintptr_t first = 0;
    unsigned count = 0;
    for (const auto& r : api::memory::scan_regions()) {
        if (r.size < val.size()) continue;
        if (!platform::is_readable(reinterpret_cast<const void*>(r.va), r.size)) continue;
        const auto* p = reinterpret_cast<const std::uint8_t*>(r.va);
        const std::size_t span = r.size - val.size() + 1;
        for (std::size_t i = 0; i < span; ++i) {
            bool match = true;
            for (std::size_t j = 0; j < val.size(); ++j) {
                if ((p[i + j] & mask[j]) != val[j]) {
                    match = false;
                    break;
                }
            }
            if (match) {
                if (count == 0) first = r.va + i;
                ++count;
                if (count > 1) {
                    err = "signature ambiguous (multiple hits)";
                    return 0;
                }
            }
        }
    }
    if (count == 0) {
        err = "signature not found";
        return 0;
    }
    return first;
}

bool looks_like_pattern(std::string_view s) {
    std::size_t hex_or_q = 0;
    for (char c : s) {
        if (std::isspace(static_cast<unsigned char>(c))) continue;
        if (c == '?' || hex_nibble(c) >= 0) ++hex_or_q;
        else return false;
    }
    return hex_or_q >= 8 && (hex_or_q % 2) == 0;
}

bool resolve_spec(lua_State* L, int idx, std::uintptr_t& out_addr, std::string& err) {
    if (lua_type(L, idx) == LUA_TNUMBER) {
        const lua_Number n = lua_tonumber(L, idx);
        if (!std::isfinite(n) || n <= 0.0 ||
            n > static_cast<lua_Number>(std::numeric_limits<std::uintptr_t>::max())) {
            err = "invalid numeric address";
            return false;
        }
        out_addr = static_cast<std::uintptr_t>(n);
        if (!platform::is_readable(reinterpret_cast<const void*>(out_addr), 1)) {
            err = "address is not mapped/readable";
            return false;
        }
        return true;
    }

    if (lua_type(L, idx) == LUA_TSTRING) {
        std::size_t len = 0;
        const char* str = lua_tolstring(L, idx, &len);
        std::string_view sv(str, len);
        if (g_table != nullptr) {
            if (const Site* s = g_table->find(sv)) {
                if (!s->resolved || s->addr == 0 || s->kind == SiteKind::Field) {
                    err = "site is unresolved or not a code location";
                    return false;
                }
                const std::uintptr_t addr = s->addr + table_delta();
                if (!platform::is_readable(reinterpret_cast<const void*>(addr), 1)) {
                    err = "resolved site address is not readable";
                    return false;
                }
                out_addr = addr;
                return true;
            }
        }
        if (looks_like_pattern(sv)) {
            std::vector<std::uint8_t> val, mask;
            if (!parse_pattern_str(sv, val, mask)) {
                err = "invalid hex signature pattern";
                return false;
            }
            const std::uintptr_t hit = scan_unique_pattern(val, mask, err);
            if (hit == 0) return false;
            out_addr = hit;
            return true;
        }
        err = "unknown site name";
        return false;
    }

    if (lua_istable(L, idx)) {
        lua_getfield(L, idx, "site");
        if (lua_isstring(L, -1)) {
            std::string_view site_name(lua_tostring(L, -1));
            lua_pop(L, 1);
            if (g_table != nullptr) {
                if (const Site* s = g_table->find(site_name)) {
                    if (s->resolved && s->addr != 0 && s->kind != SiteKind::Field) {
                        out_addr = s->addr + table_delta();
                        return platform::is_readable(reinterpret_cast<const void*>(out_addr), 1);
                    }
                }
            }
        } else {
            lua_pop(L, 1);
        }

        lua_getfield(L, idx, "pattern");
        const char* pat = lua_isstring(L, -1) ? lua_tostring(L, -1) : nullptr;
        lua_pop(L, 1);
        if (pat == nullptr) {
            err = "resolve spec table needs 'site' or 'pattern'";
            return false;
        }
        std::vector<std::uint8_t> val, mask;
        if (!parse_pattern_str(pat, val, mask)) {
            err = "invalid hex signature pattern";
            return false;
        }
        std::uintptr_t hit = scan_unique_pattern(val, mask, err);
        if (hit == 0) return false;

        lua_getfield(L, idx, "offset");
        if (lua_isnumber(L, -1)) {
            hit = static_cast<std::uintptr_t>(static_cast<std::intptr_t>(hit) +
                                             static_cast<std::intptr_t>(lua_tointeger(L, -1)));
        }
        lua_pop(L, 1);

        lua_getfield(L, idx, "xref_call");
        const bool follow_call = lua_toboolean(L, -1) != 0;
        lua_pop(L, 1);
        if (follow_call) {
            std::uint8_t insn[5]{};
            if (!platform::is_readable(reinterpret_cast<const void*>(hit), sizeof(insn)) ||
                (std::memcpy(insn, reinterpret_cast<const void*>(hit), sizeof(insn)),
                 (insn[0] != 0xE8 && insn[0] != 0xE9))) {
                err = "xref_call target is not a call/jmp rel32 instruction";
                return false;
            }
            std::int32_t rel = 0;
            std::memcpy(&rel, insn + 1, sizeof(rel));
            hit = static_cast<std::uintptr_t>(static_cast<std::intptr_t>(hit) + 5 + rel);
        }

        if (!platform::is_readable(reinterpret_cast<const void*>(hit), 1)) {
            err = "resolved target is not readable";
            return false;
        }
        out_addr = hit;
        return true;
    }

    err = "expected numeric address, site/pattern string, or spec table";
    return false;
}

bool parse_conv(std::string_view name, Conv& out) {
    if (name == "cdecl")         { out = Conv::Cdecl;    return true; }
    if (name == "stdcall")       { out = Conv::Stdcall;  return true; }
    if (name == "thiscall")      { out = Conv::Thiscall; return true; }
    if (name == "sysv")          { out = Conv::Sysv;     return true; }
    return false;
}

bool parse_val_type(std::string_view name, ValType& out, bool allow_void) {
    if (allow_void && name == "void") { out = ValType::Void; return true; }
    if (name == "i32" || name == "int")               { out = ValType::I32;  return true; }
    if (name == "u32" || name == "uint")              { out = ValType::U32;  return true; }
    if (name == "f32" || name == "float")             { out = ValType::F32;  return true; }
    if (name == "ptr" || name == "addr" || name == "pointer") { out = ValType::Ptr; return true; }
    if (name == "cstr" || name == "string")           { out = ValType::Cstr; return true; }
    if (name == "bool")                               { out = ValType::Bool; return true; }
    return false;
}

void parse_abi(lua_State* L, int idx, AbiSpec& out) {
    if (lua_isnoneornil(L, idx)) {
#if defined(__x86_64__) || defined(_M_X64)
        out.conv = Conv::Sysv;
#else
        out.conv = Conv::Cdecl;
#endif
        out.infer_args = true;
        out.ret = ValType::I32;
        return;
    }
    if (lua_type(L, idx) == LUA_TSTRING) {
        if (!parse_conv(lua_tostring(L, idx), out.conv))
            luaL_argerror(L, idx, "unknown calling convention");
        out.infer_args = true;
        out.ret = ValType::I32;
        return;
    }
    luaL_checktype(L, idx, LUA_TTABLE);
    lua_getfield(L, idx, "convention");
    if (lua_isstring(L, -1)) {
        if (!parse_conv(lua_tostring(L, -1), out.conv))
            luaL_argerror(L, idx, "unknown calling convention");
    } else {
#if defined(__x86_64__) || defined(_M_X64)
        out.conv = Conv::Sysv;
#else
        out.conv = Conv::Cdecl;
#endif
    }
    lua_pop(L, 1);

    lua_getfield(L, idx, "ret");
    if (lua_isstring(L, -1)) {
        if (!parse_val_type(lua_tostring(L, -1), out.ret, true))
            luaL_argerror(L, idx, "unknown return type");
    } else {
        out.ret = ValType::I32;
    }
    lua_pop(L, 1);

    lua_getfield(L, idx, "args");
    if (lua_istable(L, -1)) {
        out.infer_args = false;
        const int n = static_cast<int>(lua_objlen(L, -1));
        if (n > int(kMaxArgs))
            luaL_argerror(L, idx, "kp.native supports at most 8 arguments");
        out.argc = unsigned(n);
        for (int i = 0; i < n; ++i) {
            lua_rawgeti(L, -1, i + 1);
            if (!lua_isstring(L, -1) || !parse_val_type(lua_tostring(L, -1), out.args[i], false))
                luaL_argerror(L, idx, "invalid argument type in abi.args");
            lua_pop(L, 1);
        }
    } else {
        out.infer_args = true;
    }
    lua_pop(L, 1);
}

std::uintptr_t marshal_arg(lua_State* L, int slot, ValType t) {
    switch (t) {
    case ValType::I32: {
        const lua_Number n = luaL_checknumber(L, slot);
        return static_cast<std::uintptr_t>(static_cast<std::intptr_t>(n));
    }
    case ValType::U32:
    case ValType::Ptr: {
        const lua_Number n = luaL_checknumber(L, slot);
        return static_cast<std::uintptr_t>(static_cast<std::uint64_t>(n));
    }
    case ValType::Bool:
        return lua_toboolean(L, slot) ? 1u : 0u;
    case ValType::F32: {
        const float f = static_cast<float>(luaL_checknumber(L, slot));
        std::uint32_t bits = 0;
        std::memcpy(&bits, &f, sizeof(bits));
        return static_cast<std::uintptr_t>(bits);
    }
    case ValType::Cstr: {
        const char* s = lua_isnil(L, slot) ? nullptr : luaL_checkstring(L, slot);
        return reinterpret_cast<std::uintptr_t>(s);
    }
    case ValType::Void:
        return 0;
    }
    return 0;
}

std::uintptr_t infer_arg(lua_State* L, int slot) {
    switch (lua_type(L, slot)) {
    case LUA_TNIL:
        return 0;
    case LUA_TBOOLEAN:
        return lua_toboolean(L, slot) ? 1u : 0u;
    case LUA_TSTRING:
        return reinterpret_cast<std::uintptr_t>(lua_tostring(L, slot));
    case LUA_TNUMBER: {
        const lua_Number n = lua_tonumber(L, slot);
        if (n < 0.0) return static_cast<std::uintptr_t>(static_cast<std::intptr_t>(n));
        return static_cast<std::uintptr_t>(static_cast<std::uint64_t>(n));
    }
    default:
        luaL_argerror(L, slot, "unsupported argument type for inferred ABI call");
        return 0;
    }
}

#if defined(__i386__) || defined(_M_IX86)
template <typename R>
R call_cdecl(std::uintptr_t fn, unsigned argc, const std::uintptr_t* a) {
    using F0 = R (__attribute__((cdecl)) *)();
    using F1 = R (__attribute__((cdecl)) *)(std::uint32_t);
    using F2 = R (__attribute__((cdecl)) *)(std::uint32_t, std::uint32_t);
    using F3 = R (__attribute__((cdecl)) *)(std::uint32_t, std::uint32_t, std::uint32_t);
    using F4 = R (__attribute__((cdecl)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    using F5 = R (__attribute__((cdecl)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    using F6 = R (__attribute__((cdecl)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    using F7 = R (__attribute__((cdecl)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    using F8 = R (__attribute__((cdecl)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    switch (argc) {
    case 0: return reinterpret_cast<F0>(fn)();
    case 1: return reinterpret_cast<F1>(fn)(a[0]);
    case 2: return reinterpret_cast<F2>(fn)(a[0], a[1]);
    case 3: return reinterpret_cast<F3>(fn)(a[0], a[1], a[2]);
    case 4: return reinterpret_cast<F4>(fn)(a[0], a[1], a[2], a[3]);
    case 5: return reinterpret_cast<F5>(fn)(a[0], a[1], a[2], a[3], a[4]);
    case 6: return reinterpret_cast<F6>(fn)(a[0], a[1], a[2], a[3], a[4], a[5]);
    case 7: return reinterpret_cast<F7>(fn)(a[0], a[1], a[2], a[3], a[4], a[5], a[6]);
    default: return reinterpret_cast<F8>(fn)(a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]);
    }
}

template <typename R>
R call_stdcall(std::uintptr_t fn, unsigned argc, const std::uintptr_t* a) {
    using F0 = R (__attribute__((stdcall)) *)();
    using F1 = R (__attribute__((stdcall)) *)(std::uint32_t);
    using F2 = R (__attribute__((stdcall)) *)(std::uint32_t, std::uint32_t);
    using F3 = R (__attribute__((stdcall)) *)(std::uint32_t, std::uint32_t, std::uint32_t);
    using F4 = R (__attribute__((stdcall)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    using F5 = R (__attribute__((stdcall)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    using F6 = R (__attribute__((stdcall)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    using F7 = R (__attribute__((stdcall)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    using F8 = R (__attribute__((stdcall)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    switch (argc) {
    case 0: return reinterpret_cast<F0>(fn)();
    case 1: return reinterpret_cast<F1>(fn)(a[0]);
    case 2: return reinterpret_cast<F2>(fn)(a[0], a[1]);
    case 3: return reinterpret_cast<F3>(fn)(a[0], a[1], a[2]);
    case 4: return reinterpret_cast<F4>(fn)(a[0], a[1], a[2], a[3]);
    case 5: return reinterpret_cast<F5>(fn)(a[0], a[1], a[2], a[3], a[4]);
    case 6: return reinterpret_cast<F6>(fn)(a[0], a[1], a[2], a[3], a[4], a[5]);
    case 7: return reinterpret_cast<F7>(fn)(a[0], a[1], a[2], a[3], a[4], a[5], a[6]);
    default: return reinterpret_cast<F8>(fn)(a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]);
    }
}

template <typename R>
R call_thiscall(std::uintptr_t fn, unsigned argc, const std::uintptr_t* a) {
    using F1 = R (__attribute__((thiscall)) *)(std::uint32_t);
    using F2 = R (__attribute__((thiscall)) *)(std::uint32_t, std::uint32_t);
    using F3 = R (__attribute__((thiscall)) *)(std::uint32_t, std::uint32_t, std::uint32_t);
    using F4 = R (__attribute__((thiscall)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    using F5 = R (__attribute__((thiscall)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    using F6 = R (__attribute__((thiscall)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    using F7 = R (__attribute__((thiscall)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    using F8 = R (__attribute__((thiscall)) *)(std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t, std::uint32_t);
    switch (argc) {
    case 0: return reinterpret_cast<F1>(fn)(0);
    case 1: return reinterpret_cast<F1>(fn)(a[0]);
    case 2: return reinterpret_cast<F2>(fn)(a[0], a[1]);
    case 3: return reinterpret_cast<F3>(fn)(a[0], a[1], a[2]);
    case 4: return reinterpret_cast<F4>(fn)(a[0], a[1], a[2], a[3]);
    case 5: return reinterpret_cast<F5>(fn)(a[0], a[1], a[2], a[3], a[4]);
    case 6: return reinterpret_cast<F6>(fn)(a[0], a[1], a[2], a[3], a[4], a[5]);
    case 7: return reinterpret_cast<F7>(fn)(a[0], a[1], a[2], a[3], a[4], a[5], a[6]);
    default: return reinterpret_cast<F8>(fn)(a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]);
    }
}
#else
template <typename R>
R call_sysv(std::uintptr_t fn, unsigned argc, const std::uintptr_t* a) {
    using F0 = R (*)();
    using F1 = R (*)(std::uintptr_t);
    using F2 = R (*)(std::uintptr_t, std::uintptr_t);
    using F3 = R (*)(std::uintptr_t, std::uintptr_t, std::uintptr_t);
    using F4 = R (*)(std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t);
    using F5 = R (*)(std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t);
    using F6 = R (*)(std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t);
    using F7 = R (*)(std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t);
    using F8 = R (*)(std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t, std::uintptr_t);
    switch (argc) {
    case 0: return reinterpret_cast<F0>(fn)();
    case 1: return reinterpret_cast<F1>(fn)(a[0]);
    case 2: return reinterpret_cast<F2>(fn)(a[0], a[1]);
    case 3: return reinterpret_cast<F3>(fn)(a[0], a[1], a[2]);
    case 4: return reinterpret_cast<F4>(fn)(a[0], a[1], a[2], a[3]);
    case 5: return reinterpret_cast<F5>(fn)(a[0], a[1], a[2], a[3], a[4]);
    case 6: return reinterpret_cast<F6>(fn)(a[0], a[1], a[2], a[3], a[4], a[5]);
    case 7: return reinterpret_cast<F7>(fn)(a[0], a[1], a[2], a[3], a[4], a[5], a[6]);
    default: return reinterpret_cast<F8>(fn)(a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]);
    }
}
#endif

void invoke_trampoline(void* ctx) {
    auto* r = static_cast<CallRequest*>(ctx);
#if defined(__i386__) || defined(_M_IX86)
    if (r->ret_type == ValType::F32) {
        switch (r->conv) {
        case Conv::Stdcall:  r->ret_f = call_stdcall<float>(r->addr, r->argc, r->args); break;
        case Conv::Thiscall: r->ret_f = call_thiscall<float>(r->addr, r->argc, r->args); break;
        default:             r->ret_f = call_cdecl<float>(r->addr, r->argc, r->args); break;
        }
    } else {
        switch (r->conv) {
        case Conv::Stdcall:  r->ret_u = call_stdcall<std::uintptr_t>(r->addr, r->argc, r->args); break;
        case Conv::Thiscall: r->ret_u = call_thiscall<std::uintptr_t>(r->addr, r->argc, r->args); break;
        default:             r->ret_u = call_cdecl<std::uintptr_t>(r->addr, r->argc, r->args); break;
        }
    }
#else
    if (r->ret_type == ValType::F32) r->ret_f = call_sysv<float>(r->addr, r->argc, r->args);
    else                             r->ret_u = call_sysv<std::uintptr_t>(r->addr, r->argc, r->args);
#endif
}

int execute_call(lua_State* L, std::uintptr_t addr, const AbiSpec& abi, int first_arg) {
    if (!platform::is_readable(reinterpret_cast<const void*>(addr), 1))
        return luaL_error(L, "kp.native.call: target address 0x%lx is not readable",
                          static_cast<unsigned long>(addr));

    const int supplied = lua_gettop(L) - first_arg + 1;
    if (supplied < 0) return luaL_error(L, "kp.native.call: internal stack underflow");
    if (!abi.infer_args && static_cast<unsigned>(supplied) != abi.argc)
        return luaL_error(L, "kp.native.call: expected %u argument(s), got %d",
                          abi.argc, supplied);
    if (static_cast<unsigned>(supplied) > kMaxArgs)
        return luaL_error(L, "kp.native.call: at most %u arguments supported (got %d)",
                          kMaxArgs, supplied);

    CallRequest req;
    req.addr = addr;
    req.conv = abi.conv;
    req.argc = static_cast<unsigned>(supplied);
    req.ret_type = abi.ret;
    for (unsigned i = 0; i < req.argc; ++i) {
        req.args[i] = abi.infer_args
            ? infer_arg(L, first_arg + int(i))
            : marshal_arg(L, first_arg + int(i), abi.args[i]);
    }

    const bool ok = g_guard
        ? g_guard("kp.native.call", invoke_trampoline, &req)
        : (invoke_trampoline(&req), true);
    if (!ok) {
        char buf[32];
        std::snprintf(buf, sizeof(buf), "0x%llX", static_cast<unsigned long long>(addr));
        return luaL_error(L, "kp.native.call: hardware fault at %s", buf);
    }

    switch (abi.ret) {
    case ValType::Void:
        return 0;
    case ValType::I32:
        lua_pushinteger(L, static_cast<std::int32_t>(req.ret_u));
        return 1;
    case ValType::U32:
    case ValType::Ptr:
        lua_pushnumber(L, static_cast<lua_Number>(req.ret_u));
        return 1;
    case ValType::Bool:
        lua_pushboolean(L, req.ret_u != 0 ? 1 : 0);
        return 1;
    case ValType::F32:
        lua_pushnumber(L, req.ret_f);
        return 1;
    case ValType::Cstr: {
        const char* p = reinterpret_cast<const char*>(req.ret_u);
        if (p == nullptr || !platform::is_readable(p, 1)) {
            lua_pushnil(L);
            return 1;
        }
        std::size_t len = 0;
        while (len < 65536 && platform::is_readable(p + len, 1) && p[len] != '\0') ++len;
        lua_pushlstring(L, p, len);
        return 1;
    }
    }
    return 0;
}

int l_list(lua_State* L) {
    lua_newtable(L);
    if (g_table == nullptr) return 1;
    const std::uintptr_t delta = table_delta();
    int idx = 0;
    for (const Site& s : g_table->sites()) {
        if (!s.resolved || s.addr == 0 || s.kind == SiteKind::Field) continue;
        lua_createtable(L, 0, 4);
        lua_pushstring(L, s.name.c_str());
        lua_setfield(L, -2, "name");
        lua_pushnumber(L, static_cast<lua_Number>(s.addr + delta));
        lua_setfield(L, -2, "addr");
        lua_pushstring(L, s.abi.convention.empty() ? "unknown" : s.abi.convention.c_str());
        lua_setfield(L, -2, "convention");
        lua_pushstring(L, to_string(s.kind));
        lua_setfield(L, -2, "kind");
        lua_rawseti(L, -2, ++idx);
    }
    return 1;
}

int l_resolve(lua_State* L) {
    if (lua_gettop(L) < 1)
        return luaL_error(L, "kp.native.resolve expects 1 argument");
    std::uintptr_t addr = 0;
    std::string err;
    if (!resolve_spec(L, 1, addr, err)) {
        lua_pushnil(L);
        lua_pushstring(L, err.c_str());
        return 2;
    }
    lua_pushnumber(L, static_cast<lua_Number>(addr));
    return 1;
}

int l_bound_call(lua_State* L) {
    auto* fn = static_cast<BoundFn*>(luaL_checkudata(L, 1, kBoundFnType));
    return execute_call(L, fn->addr, fn->abi, 2);
}

int l_bound_tostring(lua_State* L) {
    auto* fn = static_cast<BoundFn*>(luaL_checkudata(L, 1, kBoundFnType));
    lua_pushfstring(L, "kp.native.fn(0x%p)", reinterpret_cast<void*>(fn->addr));
    return 1;
}

int l_bind(lua_State* L) {
    if (lua_gettop(L) < 1)
        return luaL_error(L, "kp.native.bind expects (spec[, abi])");
    std::uintptr_t addr = 0;
    std::string err;
    if (!resolve_spec(L, 1, addr, err))
        return luaL_error(L, "kp.native.bind: %s", err.c_str());
    AbiSpec abi;
    parse_abi(L, 2, abi);

    auto* fn = static_cast<BoundFn*>(lua_newuserdata(L, sizeof(BoundFn)));
    fn->addr = addr;
    fn->abi = abi;
    luaL_getmetatable(L, kBoundFnType);
    lua_setmetatable(L, -2);
    return 1;
}

int l_call(lua_State* L) {
    if (lua_gettop(L) < 1)
        return luaL_error(L, "kp.native.call expects (target, abi, ...)");
    std::uintptr_t addr = 0;
    std::string err;
    if (!resolve_spec(L, 1, addr, err))
        return luaL_error(L, "kp.native.call: %s", err.c_str());
    AbiSpec abi;
    parse_abi(L, 2, abi);
    return execute_call(L, addr, abi, 3);
}

}  // namespace

void bind(const AddressTable* table, std::uintptr_t runtime_base, Guard guard) {
    g_table = table;
    g_runtime_base = runtime_base;
    g_guard = guard;
}

void register_all(lua_State* L) {
    if (luaL_newmetatable(L, kBoundFnType)) {
        lua_pushcfunction(L, l_bound_call);
        lua_setfield(L, -2, "__call");
        lua_pushcfunction(L, l_bound_tostring);
        lua_setfield(L, -2, "__tostring");
        lua_pushboolean(L, 0);
        lua_setfield(L, -2, "__metatable");
    }
    lua_pop(L, 1);

    lua_getglobal(L, "kp");
    if (!lua_istable(L, -1)) {
        lua_pop(L, 1);
        lua_createtable(L, 0, 1);
        lua_pushvalue(L, -1);
        lua_setglobal(L, "kp");
    }
    lua_getfield(L, -1, "native");
    if (!lua_istable(L, -1)) {
        lua_pop(L, 1);
        lua_createtable(L, 0, 4);
        lua_pushvalue(L, -1);
        lua_setfield(L, -3, "native");
    }
    lua_pushcfunction(L, l_list);    lua_setfield(L, -2, "list");
    lua_pushcfunction(L, l_resolve); lua_setfield(L, -2, "resolve");
    lua_pushcfunction(L, l_bind);    lua_setfield(L, -2, "bind");
    lua_pushcfunction(L, l_call);    lua_setfield(L, -2, "call");
    lua_pop(L, 2);
}

}  // namespace kp::hooks::native
