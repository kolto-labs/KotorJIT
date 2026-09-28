#pragma once
#include <cstdint>
// Layout produced by PUSHFD; PUSHAD. original_esp is supplied separately,
// before the first push. All slots are actual i386 values, never guessed
// locals.
struct ProjectileRegisters {
  std::uint32_t edi, esi, ebp, pushad_esp, ebx, edx, ecx, eax;
};
extern "C" int kp_projectile_dispatch(const ProjectileRegisters *,
                                      const std::uint32_t *original_esp);
extern "C" void kp_projectile_entry();
