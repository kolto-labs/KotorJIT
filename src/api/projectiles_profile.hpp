#pragma once
#include <array>
#include <cstdint>
namespace kp::api::projectiles {
enum Site {
  Load,
  Receiver,
  Exists,
  ResRefCtor,
  StringCtor,
  StringDtor,
  TableString,
  Player,
  Convert,
  Creature,
  SiteCount
};
struct Guard {
  std::uintptr_t va;
  const char *bytes;
  int relocated = -1;
};
struct Profile {
  const char *sha;
  const char *name;
  std::uintptr_t base, manager, resources, rules, projectile_vtable,
      return_address;
  std::array<Guard, SiteCount> sites;
};
const Profile &profile();
} // namespace kp::api::projectiles
