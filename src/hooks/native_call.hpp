// Arbitrary signature-backed native engine function resolution & typed calls.
//
// Exposes kp.native.{list, resolve, bind, call} using AddressTable sites,
// unique masked signatures over bound executable memory regions, and the
// runtime's hardware fault guard so bad pointers raise clean Lua errors
// instead of crashing the game process.
#pragma once

#include <cstdint>

#include "hooks/registry.hpp"

struct lua_State;

namespace kp::hooks::native {

using Guard = bool (*)(const char* label, void (*work)(void*), void* ctx);

void bind(const AddressTable* table, std::uintptr_t runtime_base, Guard guard = nullptr);
void register_all(lua_State* L);

}  // namespace kp::hooks::native
