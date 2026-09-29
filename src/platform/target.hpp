// What the runtime is compiled for, stated once.
//
// Two engine ABIs exist in the supported set:
//
//   i386   The Windows PE builds (MSVC __thiscall, callee-pops) and the K2 Linux
//          ELF (GCC cdecl with `this` on the stack). Pointers and the engine's
//          `unsigned long` object ids are 32 bits.
//
//   x86_64 The macOS Steam builds (Aspyr, clang, Itanium C++ ABI, System V
//          calling convention). `this` is the first integer argument (RDI),
//          the caller cleans, and the engine's object id type is a 64-bit
//          `unsigned long long` in registers AND in memory: CScriptEvent's
//          object list stores 8-byte elements and StackPopObject writes 8
//          bytes (both verified by disassembly, see
//          data/adjudication/mac_x64_bindings.json). A 32-bit out-parameter
//          there would be a stack overwrite.
//
// A Linux x86_64 build of the same sources exists only as the offline test
// host for the x86_64 engine ABI (same calling convention and layouts). It is
// never shipped and never meets a game.
#pragma once

#include <cstdint>
#include <type_traits>

#if defined(__APPLE__) || defined(KP_DARWIN_SHIM)
#define KP_DARWIN 1
#else
#define KP_DARWIN 0
#endif

#if defined(__x86_64__) || defined(_M_X64)
#define KP_X64 1
#else
#define KP_X64 0
#endif

namespace kp::abi {

inline constexpr bool kX64 = KP_X64 != 0;
inline constexpr bool kDarwin = KP_DARWIN != 0;

// The engine's object-id type as it crosses a call boundary or sits in engine
// memory. Values themselves always fit in 32 bits (OBJECT_INVALID is
// 0x7f000000); scripts only ever see the low 32 bits.
using ObjectId = std::conditional_t<kX64, std::uint64_t, std::uint32_t>;

// Truncate an engine id to the 32-bit value scripts see.
constexpr std::uint32_t script_id(ObjectId v) { return static_cast<std::uint32_t>(v); }

}  // namespace kp::abi
