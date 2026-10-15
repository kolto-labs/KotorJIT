#pragma once

#include "hooks/registry.hpp"
#include <atomic>
#include <cstddef>

struct lua_State;
namespace kp::hooks::lua_bridge {

inline constexpr unsigned max_stack_bytes = 256;
// A private replay copy: the caller's stack arguments are never modified.
struct HookCtx {
    std::uint32_t ecx, edx, eax, edx_ret;
    alignas(4) unsigned char st0[12]; // x87 extended precision, not rounded to double
    std::uint32_t args[max_stack_bytes / 4];
    bool entered, failed, skip, post;
};

// Empty means admitted. Structural/layout checks additionally fail closed.
std::string refusal(const Site&);

class Entry {
public:
    using Dispatch = bool (*)(void*, Entry&, HookCtx&, bool post);
    using Gate = bool (*)();
    ~Entry();
    Entry(const Entry&) = delete;
    Entry& operator=(const Entry&) = delete;
    Entry() = default;
    // Caller must guarantee a quiescent patch point, as for Detour itself.
    bool install(const Site&, std::uintptr_t address, Dispatch, void*, Gate, std::string&);
    bool uninstall();
    Site site;
    std::atomic<bool> poisoned{false};
    bool active() const { return busy_; }
    int pre(HookCtx&);
    void post(HookCtx&);
private:
    Detour detour_;
    void* stub_ = nullptr;
    std::size_t stub_size_ = 0;
    void* original_ = nullptr;
    bool busy_ = false;
    Dispatch dispatch_ = nullptr;
    void* user_ = nullptr;
    Gate gate_ = nullptr;
};

// Guard runs work under the host's hardware fault recovery frame. On a fault
// it must return false, poison the entry, and disable the affected Lua runtime.
using Guard = bool (*)(Entry&, void (*work)(void*), void*);
using Review = bool (*)(const Site&);
// Binding/unbinding and registration belong to quiescent engine-thread points.
void bind(const AddressTable*, std::uintptr_t base, Entry::Gate live_gate,
          Entry::Gate patch_gate, Guard, Review = nullptr);
void register_all(lua_State*);
void close_state(lua_State*);
void shutdown();
} // namespace kp::hooks::lua_bridge
