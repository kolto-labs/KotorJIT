#include "hooks/lua_bridge.hpp"
#include "platform/platform.hpp"
#include <algorithm>
#include <cstring>
#include <set>

namespace kp::hooks::lua_bridge {
std::string refusal(const Site& s) {
    const auto& a = s.abi;
    if (s.hook_refused || a.hook_safe == "refuse") return "hook.safe=refuse";
    if (a.hook_safe != "static_ok" || !a.engine_accept) return "hook engine acceptance not established";
    if (a.confidence != "proven" && a.confidence != "consistent") return "ABI confidence is not proven or consistent";
    if (a.variadic || a.struct_return) return "variadic or struct-return ABI";
    if (a.convention != "cdecl" && a.convention != "stdcall" && a.convention != "thiscall" && a.convention != "fastcall") return "unsupported convention";
    if (a.stack_bytes < 0 || a.stack_bytes > int(max_stack_bytes) || a.stack_bytes % 4) return "invalid or oversized stack window";
    if (a.ret_pop < 0 || (a.convention == "cdecl" ? a.ret_pop != 0 : a.ret_pop != a.stack_bytes)) return "cleanup count disagrees with convention";
    if (a.observed_ret.empty()) return "no observed RET cleanup evidence";
    for (int n : a.observed_ret) if (n != a.ret_pop) return "observed RET disagrees with cleanup count";
    if (!a.cleanup_by.empty() && a.cleanup_by != (a.convention == "cdecl" ? "caller" : "callee")) return "cleanup owner disagrees with convention";
    if (a.ret_storage != "EAX" && a.ret_storage != "EDX:EAX" && a.ret_storage != "ST0" && a.ret_storage != "void") return "unsupported return storage";
    if (a.ret_storage=="EAX" && a.ret_lua!="integer" && ! (a.ret_lua=="address" || a.ret_lua=="cexostring_ptr")) return "unsupported EAX return type";
    if (a.ret_storage=="EDX:EAX" && a.ret_lua!="int64" && a.ret_lua!="integer") return "unsupported EDX:EAX return type";
    if (a.ret_storage=="ST0" && a.ret_lua!="number") return "unsupported ST0 return type";
    if ((a.convention == "thiscall" && a.this_reg != "ECX") || (!a.this_reg.empty() && a.this_reg != "ECX")) return "unsupported this storage";
    std::set<int> indices, bytes;
    std::set<std::string> regs;
    for (const auto& p : a.params) {
        if (p.index < 0 || !indices.insert(p.index).second) return "missing or duplicate parameter index";
        if (p.size != 1 && p.size != 2 && p.size != 4 && p.size != 8) return "unsupported parameter width";
        if (p.lua != "integer" && p.lua != "number" && p.lua != "address" && p.lua != "cexostring_ptr" && p.lua != "int64") return "unsupported Lua parameter type: " + p.lua;
        if (p.lua == "number" && p.size != 4 && p.size != 8) return "unsupported floating parameter width";
        if ((p.lua == "address" || p.lua == "cexostring_ptr") && p.size != 4) return "unsupported pointer width";
        if (!p.reg.empty()) {
            if (p.stack != -1 || p.size > 4 || (p.reg != "ECX" && p.reg != "EDX") ||
                a.convention != "fastcall" || !regs.insert(p.reg).second || p.reg == a.this_reg) return "invalid register parameter";
        } else {
            if (p.stack < 4 || p.stack % 4 || p.stack - 4 > a.stack_bytes - p.size) return "parameter outside stack window";
            for (int b = p.stack; b < p.stack + ((p.size+3)&~3); ++b)
                if (!bytes.insert(b).second) return "overlapping parameters";
        }
    }
    if(bytes.size()!=static_cast<std::size_t>(a.stack_bytes)) return "incomplete stack parameter contract";
    for(int i=0;i<int(indices.size());++i) if(!indices.count(i)) return "non-contiguous parameter indices";
    return {};
}

extern "C" int kp_hook_pre(Entry* entry, HookCtx* ctx) { return entry->pre(*ctx); }
extern "C" void kp_hook_post(Entry* entry, HookCtx* ctx) { entry->post(*ctx); }

int Entry::pre(HookCtx& c) {
    c.entered = c.failed = c.skip = c.post = false;
    c.eax = c.edx_ret = 0;
    std::memset(c.st0, 0, sizeof c.st0);
    // The gate is tested BEFORE the non-atomic per-engine-thread busy flag.
    if (!gate_ || !gate_() || poisoned.load(std::memory_order_acquire) || busy_) return 0;
    busy_ = c.entered = true;
    const HookCtx before = c;
    if (!dispatch_(user_, *this, c, false)) {
        c = before;
        c.failed = true;
    }
    return c.skip ? 1 : 0;
}
void Entry::post(HookCtx& c) {
    if (!c.entered) return;
    if (!c.failed && !poisoned.load(std::memory_order_acquire) && gate_ && gate_()) {
        c.post = true;
        const HookCtx before = c;
        if (!dispatch_(user_, *this, c, true)) c = before;
    }
    busy_ = false;
}

namespace {
struct Emitter {
    std::vector<std::uint8_t> bytes;
    void b(unsigned x) { bytes.push_back(static_cast<std::uint8_t>(x)); }
    void d(std::uint32_t x) { for (int i = 0; i != 4; ++i) b(x >> (8*i)); }
    void seq(std::initializer_list<unsigned> xs) { for (unsigned x : xs) b(x); }
    void store(unsigned modrm, unsigned off) { seq({0x89, modrm}); d(off); }
    void load(unsigned modrm, unsigned off) { seq({0x8b, modrm}); d(off); }
    void helper(void* fn, Entry* entry) {
        seq({0x83,0xec,0x08,0x53,0x68}); d(reinterpret_cast<std::uintptr_t>(entry));
        b(0xb8); d(reinterpret_cast<std::uintptr_t>(fn)); seq({0xff,0xd0,0x83,0xc4,0x10});
    }
};
}

bool Entry::install(const Site& s, std::uintptr_t addr, Dispatch dispatch, void* user,
                    Gate gate, std::string& error) {
    error = refusal(s);
    if (!error.empty()) return false;
    if (stub_ || !dispatch || !gate || !s.resolved || !addr) { error = "invalid or already installed entry"; return false; }
    site = s; dispatch_ = dispatch; user_ = user; gate_ = gate;
    Emitter e;
    // EBP anchors caller arguments, EBX anchors aligned context, nonvolatile
    // registers are restored. Every C++ and replay call has 16-byte-aligned ESP.
    e.seq({0x55,0x89,0xe5,0x53,0x56,0x57,0x83,0xe4,0xf0,0x81,0xec});
    e.d((sizeof(HookCtx)+15)&~15u); e.seq({0x89,0xe3});
    e.store(0x8b, offsetof(HookCtx,ecx)); e.store(0x93, offsetof(HookCtx,edx));
    for (int off=0; off<s.abi.stack_bytes; off+=4) {
        e.load(0x85, 8+off); e.store(0x83, offsetof(HookCtx,args)+off);
    }
    e.helper(reinterpret_cast<void*>(&kp_hook_pre), this);
    e.seq({0x85,0xc0,0x0f,0x85}); auto skip=e.bytes.size(); e.d(0);
    unsigned pad = (16-(s.abi.stack_bytes%16))%16;
    if (pad) e.seq({0x83,0xec,pad});
    for (int off=s.abi.stack_bytes-4; off>=0; off-=4) {
        e.seq({0xff,0xb3}); e.d(offsetof(HookCtx,args)+off);
    }
    e.load(0x8b,offsetof(HookCtx,ecx)); e.load(0x93,offsetof(HookCtx,edx));
    e.b(0xa1); e.d(reinterpret_cast<std::uintptr_t>(&original_)); e.seq({0xff,0xd0});
    e.seq({0x89,0xdc}); // discard replay window regardless of cleanup convention
    e.store(0x83,offsetof(HookCtx,eax)); e.store(0x93,offsetof(HookCtx,edx_ret));
    if (s.abi.ret_storage=="ST0") { e.seq({0xdb,0xbb}); e.d(offsetof(HookCtx,st0)); }
    std::uint32_t rel=e.bytes.size()-(skip+4); std::memcpy(e.bytes.data()+skip,&rel,4);
    e.helper(reinterpret_cast<void*>(&kp_hook_post), this);
    e.load(0x83,offsetof(HookCtx,eax)); e.load(0x93,offsetof(HookCtx,edx_ret));
    if (s.abi.ret_storage=="ST0") { e.seq({0xdb,0xab}); e.d(offsetof(HookCtx,st0)); }
    e.seq({0x8d,0x65,0xf4,0x5f,0x5e,0x5b,0x5d,0xc2});
    e.b(s.abi.ret_pop); e.b(s.abi.ret_pop>>8);
    stub_size_=e.bytes.size(); stub_=platform::alloc_exec(stub_size_);
    if (!stub_) { error="stub allocation failed"; return false; }
    std::memcpy(stub_,e.bytes.data(),stub_size_);
    if (!platform::commit_exec(stub_,stub_size_)) {
        error="stub executable protection failed"; platform::free_exec(stub_,stub_size_); stub_=nullptr; return false;
    }
    platform::flush_instruction_cache(stub_,stub_size_);
    const auto publish = +[](void* o, void* u) {
        __atomic_store_n(static_cast<void**>(u), o, __ATOMIC_RELEASE);
    };
    const auto st=detour_.install(reinterpret_cast<void*>(addr),stub_,s.expected.data(),s.expected.size(),&error,publish,&original_);
    if (st!=HookStatus::Ok) { __atomic_store_n(&original_,nullptr,__ATOMIC_RELEASE); platform::free_exec(stub_,stub_size_); stub_=nullptr; return false; }
    return true;
}
bool Entry::uninstall() {
    if (busy_) return false;
    __atomic_store_n(&original_,nullptr,__ATOMIC_RELEASE);
    if (detour_.installed() && detour_.uninstall()!=HookStatus::Ok) {
        __atomic_store_n(&original_,detour_.original(),__ATOMIC_RELEASE);
        return false;
    }
    if (stub_) platform::free_exec(stub_,stub_size_);
    stub_=nullptr;
    return true;
}
Entry::~Entry() { uninstall(); }
} // namespace kp::hooks::lua_bridge
