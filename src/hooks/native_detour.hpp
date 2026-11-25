// The detour engine for the architecture this runtime is compiled for.
//
// registry.cpp is written against one small contract -- install(target,
// detour, expect, len, detail), uninstall(), original() and a HookStatus with
// Ok and to_string -- and this header supplies it:
//
//   i386    hooks/trampoline.hpp as-is: a 5-byte rel32 jump.
//   x86_64  hooks/x64/trampoline.hpp behind a thin adapter: a 14-byte
//           absolute jump, RIP-relative/rel32/rel8 relocation and a near
//           trampoline page. That engine reports a `const char*` detail;
//           the adapter copies it into the std::string the registry wants.
#pragma once

#if defined(__x86_64__) || defined(_M_X64)

#include <string>

#include "hooks/x64/trampoline.hpp"

namespace kp::hooks {

using HookStatus = x64::HookStatus;
using TrampolineFn = x64::TrampolineFn;
using x64::to_string;

class Detour {
public:
    HookStatus install(void* target, void* detour, const std::uint8_t* expect = nullptr,
                       std::size_t expect_len = 0, std::string* detail = nullptr,
                       TrampolineFn on_trampoline = nullptr, void* trampoline_user = nullptr) {
        const char* why = nullptr;
        const HookStatus st = impl_.install(target, detour, expect, expect_len, &why,
                                            on_trampoline, trampoline_user);
        if (detail != nullptr && why != nullptr) *detail = why;
        return st;
    }
    HookStatus uninstall(std::string* detail = nullptr) {
        const char* why = nullptr;
        const HookStatus st = impl_.uninstall(&why);
        if (detail != nullptr && why != nullptr) *detail = why;
        return st;
    }
    void* original() const { return impl_.original(); }
    bool installed() const { return impl_.installed(); }
    std::size_t stolen_bytes() const { return impl_.stolen_bytes(); }

private:
    x64::Detour impl_;
};

}  // namespace kp::hooks

#else

#include "hooks/trampoline.hpp"

#endif
