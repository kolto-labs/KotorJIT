#ifdef NDEBUG
#undef NDEBUG
#endif
#include "api/projectiles.hpp"
#include "api/projectiles_entry.hpp"
#include "api/projectiles_patch.hpp"
#include <cassert>
#include <cstring>
#include <functional>
#include <iostream>
extern "C" {
#include "lauxlib.h"
#include "lua.h"
#include "lualib.h"
}
using namespace kp::api::projectiles;
namespace kp::api {
void push_kp_table(lua_State *L) {
  lua_getglobal(L, "kp");
  if (lua_isnil(L, -1)) {
    lua_pop(L, 1);
    lua_newtable(L);
    lua_pushvalue(L, -1);
    lua_setglobal(L, "kp");
  }
}
} // namespace kp::api
Ref ref(const char *s) {
  Ref r{};
  std::memcpy(r.data(), s, std::strlen(s));
  return r;
}
struct Fake : Backend {
  std::uint32_t pc = 42;
  bool pc_ok = true;
  Address table = 77;
  unsigned loads = 0;
  int result = 1;
  Ref selected{};
  std::function<void()> onload;
  bool prepare(const std::string &s, Config &out, std::string &error) override {
    if (s != "plc_footlker" && s != "plc_crate") {
      error = "missing model";
      return false;
    }
    out.model = ref(s.c_str());
    out.table = table;
    out.ammo[0] = {1, 0, ref("w_laserfire_r")};
    out.count = 1;
    return true;
  }
  bool current_pc(std::uint32_t &out) override {
    out = pc;
    return pc_ok;
  }
  Address ammunition_table() override { return table; }
  int load(const Context &c, const Ref *replacement) override {
    ++loads;
    selected = replacement ? *replacement : c.original;
    if (onload) {
      auto callback = onload;
      callback();
    }
    return result;
  }
};
extern "C" {
std::uint32_t abi_before = 0, abi_after[8] = {};
char abi_ref[16] = "w_laserfire_r";
unsigned abi_calls = 0;
__attribute__((thiscall, noinline)) int abi_original(void *self,
                                                     const void *resource,
                                                     std::uint32_t a,
                                                     std::uint32_t b) {
  assert(self == reinterpret_cast<void *>(0x1234));
  assert(resource == abi_ref);
  assert(a == 0xff && b == 0x5678);
  ++abi_calls;
  return 0x12345;
}
__attribute__((force_align_arg_pointer)) int
kp_projectile_dispatch(const ProjectileRegisters *r, const std::uint32_t *sp) {
  assert(r->ecx == 0x1234 && r->edi == 0x11111111 && r->esi == 0x22222222 &&
         r->ebx == 0x33333333 && r->ebp == 0x44444444);
  assert(*reinterpret_cast<const std::uint32_t *>(
             reinterpret_cast<const char *>(sp) + 0x9c) == 0xabcdef01);
  assert(*reinterpret_cast<const std::uint32_t *>(
             reinterpret_cast<const char *>(sp) + 0x24) == 0x10203040);
  assert(reinterpret_cast<std::uintptr_t>(sp) == abi_before - 16);
  return abi_original(reinterpret_cast<void *>(r->ecx),
                      reinterpret_cast<void *>(sp[1]), sp[2], sp[3]);
}
__attribute__((naked)) void run_abi() {
  __asm__ volatile(
      "pushl %ebp\n\tpushl %ebx\n\tpushl %esi\n\tpushl %edi\n\tsubl "
      "$160,%esp\n\t"
      "movl $0xabcdef01,140(%esp)\n\tmovl $0x10203040,20(%esp)\n\tmovl "
      "%esp,abi_before\n\t"
      "movl $0x11111111,%edi\n\tmovl $0x22222222,%esi\n\tmovl "
      "$0x33333333,%ebx\n\tmovl $0x44444444,%ebp\n\t"
      "movl $0x1234,%ecx\n\tpushl $0x5678\n\tpushl $255\n\tpushl "
      "$abi_ref\n\tstc\n\tcall kp_projectile_entry\n\t"
      "movl %eax,abi_after\n\tmovl %esp,abi_after+4\n\tmovl "
      "%edi,abi_after+8\n\tmovl %esi,abi_after+12\n\tmovl "
      "%ebx,abi_after+16\n\tmovl %ebp,abi_after+20\n\tmovl "
      "%ecx,abi_after+24\n\tpushfl\n\tpopl %eax\n\tmovl %eax,abi_after+28\n\t"
      "addl $160,%esp\n\tpopl %edi\n\tpopl %esi\n\tpopl %ebx\n\tpopl "
      "%ebp\n\tret\n\t");
}
}

struct FakeSlot : SlotAccess {
  std::uintptr_t value = 11;
  std::uint32_t protection = 2;
  bool fail_write = false, fail_restore = false, fail_exchange = false;
  std::uintptr_t race = 0;
  unsigned exchanges = 0;
  bool writable(std::uintptr_t, std::uint32_t &previous) override {
    if (fail_write)
      return false;
    previous = protection;
    protection = 4;
    return true;
  }
  bool restore(std::uintptr_t, std::uint32_t previous) override {
    if (fail_restore)
      return false;
    protection = previous;
    return true;
  }
  bool exchange(std::uintptr_t, std::uintptr_t expected, std::uintptr_t desired,
                std::uintptr_t &observed) override {
    ++exchanges;
    if (fail_exchange)
      return false;
    if (race) {
      value = race;
      race = 0;
    }
    observed = value;
    if (value == expected)
      value = desired;
    return true;
  }
};
void test_slot_transaction() {
  std::string error;
  {
    FakeSlot io;
    SlotPatch p;
    io.fail_write = true;
    assert(!p.install(io, 100, 11, 22, error) && !p.pending() &&
           io.value == 11 && io.protection == 2 && io.exchanges == 0);
  }
  {
    FakeSlot io;
    SlotPatch p;
    io.fail_exchange = true;
    assert(!p.install(io, 100, 11, 22, error) && !p.pending() &&
           io.value == 11 && io.protection == 2);
  }
  {
    FakeSlot io;
    SlotPatch p;
    io.race = 33;
    assert(!p.install(io, 100, 11, 22, error) && !p.pending() &&
           io.value == 33 && io.protection == 2);
  }
  {
    FakeSlot io;
    SlotPatch p;
    io.fail_restore = true;
    assert(!p.install(io, 100, 11, 22, error) && p.pending() && p.owns_slot() &&
           p.protection_pending() && io.value == 22);
    assert(!p.install(io, 100, 11, 22, error));
    io.fail_write = true;
    assert(!p.remove(io, error) && p.owns_slot() && io.value == 22);
    io.fail_write = false;
    io.fail_restore = false;
    assert(p.remove(io, error) && !p.pending() && io.value == 11 &&
           io.protection == 2);
  }
  {
    FakeSlot io;
    SlotPatch p;
    assert(p.install(io, 100, 11, 22, error));
    io.fail_exchange = true;
    assert(!p.remove(io, error) && p.owns_slot() && io.value == 22 &&
           io.protection == 2);
    io.fail_exchange = false;
    io.fail_restore = true;
    assert(!p.remove(io, error) && p.pending() && !p.owns_slot() &&
           p.protection_pending() && io.value == 11);
    unsigned exchanges = io.exchanges;
    io.value = 33;
    io.fail_restore = false;
    assert(p.remove(io, error) && !p.pending() && io.value == 33 &&
           io.protection == 2 && io.exchanges == exchanges);
  }
  {
    FakeSlot io;
    SlotPatch p;
    assert(p.install(io, 100, 11, 22, error));
    io.value = 33;
    assert(p.remove(io, error) && !p.pending() && io.value == 33 &&
           io.protection == 2 && error.find("foreign") != std::string::npos);
  }
  {
    FakeSlot io;
    SlotPatch p;
    io.race = 33;
    io.fail_restore = true;
    assert(!p.install(io, 100, 11, 22, error) && p.pending() &&
           !p.owns_slot() && io.value == 33);
    unsigned exchanges = io.exchanges;
    io.fail_restore = false;
    assert(p.remove(io, error) && !p.pending() && io.value == 33 &&
           io.protection == 2 && exchanges == io.exchanges);
  }
  {
    Fake b;
    Service s;
    std::string e;
    s.bind(&b, "test", "synthetic");
    assert(s.configure("plc_crate", e));
    s.suspend("protection restoration pending");
    auto before = s.status();
    assert(!before.supported && !before.enabled && !before.observing);
    assert(!s.configure("plc_crate", e) && !s.observe(true, e));
    Context c;
    assert(s.intercept(c) == 1 && b.loads == 1 && s.records().empty());
  }
}
int main() {
  test_slot_transaction();
  run_abi();
  assert(abi_calls == 1 && abi_after[0] == 0x12345 &&
         abi_after[1] == abi_before);
  assert(abi_after[2] == 0x11111111 && abi_after[3] == 0x22222222 &&
         abi_after[4] == 0x33333333 && abi_after[5] == 0x44444444 &&
         abi_after[6] == 0x1234);
  assert(abi_after[7] & 1);
  Fake b;
  Service s;
  s.bind(&b, "verified test", "synthetic");
  Context c;
  c.receiver = true;
  c.source = 42;
  c.target = 99;
  c.row = 1;
  c.original = ref("w_laserfire_r");
  std::string error;
  assert(s.intercept(c) == 1 && b.loads == 1 && s.records().empty());
  assert(s.observe(true, error));
  assert(s.intercept(c) == 1);
  assert(std::strcmp(s.records().back().reason, "stock_observation") == 0);
  assert(s.configure("plc_footlker", error));
  auto version = s.status().version;
  assert(s.intercept(c) == 1 && b.selected == ref("plc_footlker"));
  assert(s.records().back().replaced);
  assert(!s.configure("missing", error) && s.status().version == version);
  assert(!s.configure("bad/name", error));
  assert(!s.configure(std::string("ok\0bad", 6), error));
  c.source = 43;
  s.intercept(c);
  assert(!s.records().back().replaced &&
         std::strcmp(s.records().back().reason, "non_pc") == 0);
  b.pc = 43;
  s.intercept(c);
  assert(s.records().back().replaced); // Fresh PC switching.
  c.row = 2;
  s.intercept(c);
  assert(!s.records().back().replaced);
  c.row = 1;
  c.variant = 1;
  s.intercept(c);
  assert(!s.records().back().replaced);
  c.variant = 0;
  b.table = 78;
  s.intercept(c);
  assert(std::strcmp(s.records().back().reason, "ammunition_table_changed") ==
         0);
  b.table = 77;
  b.result = 0;
  auto calls = b.loads;
  s.intercept(c);
  assert(b.loads == calls + 1 &&
         !s.records().back().load_ok); // No unsafe fallback retry.
  b.result = 1;
  b.onload = [&] {
    b.onload = nullptr;
    assert(s.configure("plc_crate", error));
  };
  s.intercept(c);
  assert(b.selected == ref("plc_footlker") &&
         s.records().back().version == version);
  s.intercept(c);
  assert(b.selected == ref("plc_crate"));
  s.disable();
  s.intercept(c);
  assert(!s.records().back().replaced && b.selected == c.original);
  c.receiver = false;
  s.intercept(c);
  assert(std::strcmp(s.records().back().reason, "other_callsite") == 0);
  for (int i = 0; i < 140; ++i) {
    s.intercept(c);
  }
  assert(s.records().size() == 128 && s.status().dropped > 0);
  auto epoch = s.status().epoch;
  s.bind(&b, "rebind", "synthetic");
  assert(s.status().epoch > epoch && s.records().empty() &&
         !s.status().enabled);
  service().bind(&b, "test", "synthetic");
  lua_State *L = luaL_newstate();
  luaL_openlibs(L);
  register_all(L);
  const char *script =
      "assert(kp.projectiles.status().supported); local "
      "a=assert(kp.projectiles.configure{model='plc_crate'}); assert(a.enabled "
      "and a.model=='plc_crate'); local "
      "x,e=kp.projectiles.configure{model='missing'}; assert(x==nil and "
      "type(e)=='string'); assert(kp.projectiles.status().version==a.version); "
      "assert(kp.projectiles.disable().enabled==false); "
      "assert(#kp.projectiles.records()==0)";
  if (luaL_dostring(L, script)) {
    std::cerr << lua_tostring(L, -1) << '\n';
    return 1;
  }
  lua_close(L);
  std::cout
      << "projectile service, Lua contract, and real i386 entry ABI passed\n";
}
