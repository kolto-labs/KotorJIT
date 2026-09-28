#include "api/projectiles.hpp"
#include "api/projectiles_entry.hpp"
#include "api/projectiles_patch.hpp"
#include "api/projectiles_profile.hpp"
#include <cstring>
#ifdef _WIN32
#include "image/loaded_image.hpp"
#include <windows.h>
#endif
namespace kp::api::projectiles {
#ifdef _WIN32
namespace {
struct EngineString {
  char *data = nullptr;
  std::uint32_t length = 0;
};
class Native final : public Backend {
public:
  Address base = 0;
  void *original = nullptr;
  SlotPatch patch;
  Address at(Address va) const { return base + va - profile().base; }
  template <class R, class... A> R call(Site s, void *self, A... args) const {
    using F = R(__attribute__((thiscall)) *)(void *, A...);
    return reinterpret_cast<F>(at(profile().sites[s].va))(self, args...);
  }
  bool read(Address a, void *dst, std::size_t size) const {
    image::LiveImage live(0);
    return a && live.read(a, dst, size);
  }
  Address ptr(Address a) const {
    Address p = 0;
    return read(a, &p, sizeof p) ? p : 0;
  }
  bool guards(std::string &error) const {
    for (const auto &s : profile().sites) {
      unsigned char expected[32]{}, actual[32]{};
      auto n = std::strlen(s.bytes) / 2;
      for (unsigned i = 0; i < n; ++i) {
        auto d = [](char c) { return c <= '9' ? c - '0' : c - 'a' + 10; };
        expected[i] = (d(s.bytes[2 * i]) << 4) | d(s.bytes[2 * i + 1]);
      }
      if (s.relocated >= 0) {
        std::uint32_t v;
        std::memcpy(&v, expected + s.relocated, 4);
        v = at(v);
        std::memcpy(expected + s.relocated, &v, 4);
      }
      if (!read(at(s.va), actual, n) || std::memcmp(expected, actual, n)) {
        error = "projectile native code guard mismatch";
        return false;
      }
    }
    if (ptr(at(profile().projectile_vtable) + 0x78) !=
        at(profile().sites[Load].va)) {
      error = "projectile vtable load slot mismatch";
      return false;
    }
    return true;
  }
  bool current_pc(std::uint32_t &id) override {
    Address manager = ptr(at(profile().manager)), client = ptr(manager + 4),
            server = ptr(manager + 8);
    if (!manager || !client || !server || !ptr(client + 4) || !ptr(server + 4))
      return false;
    auto sid = call<std::uint32_t>(Player, reinterpret_cast<void *>(server));
    if (sid == 0x7f000000)
      return false;
    id = call<std::uint32_t>(Convert, reinterpret_cast<void *>(client), sid);
    if (id == 0x7f000000)
      return false;
    auto creature =
        call<Address>(Creature, reinterpret_cast<void *>(client), id);
    unsigned char type = 0;
    return creature && read(creature + 8, &type, 1) && type == 5;
  }
  Address ammunition_table() override {
    Address rules = ptr(at(profile().rules)), tables = ptr(rules + 0xb8);
    return rules && tables ? ptr(tables + 0x64) : 0;
  }
  Ref ref(const std::string &name) {
    Ref result{};
    call<void *>(ResRefCtor, result.data(), name.c_str());
    return result;
  }
  bool table_entry(Address table, unsigned row, const char *key,
                   std::string &out) {
    EngineString column, value;
    call<void *>(StringCtor, &column, key);
    int ok = call<int>(TableString, reinterpret_cast<void *>(table), int(row),
                       &column, &value);
    // Results are bounded before copying. Destructor always releases engine
    // allocation.
    char bounded[65]{};
    bool valid =
        ok && value.data && value.length <= 65 &&
        read(reinterpret_cast<Address>(value.data), bounded, value.length);
    if (valid) {
      auto end =
          static_cast<const char *>(std::memchr(bounded, 0, sizeof bounded));
      valid = end != nullptr;
      if (valid)
        out.assign(bounded, end - bounded);
    }
    call<void>(StringDtor, &value);
    call<void>(StringDtor, &column);
    return valid;
  }
  bool prepare(const std::string &name, Config &next,
               std::string &error) override {
    Address manager = ptr(at(profile().resources));
    if (!manager) {
      error = "resource manager unavailable";
      return false;
    }
    next.model = ref(name);
    for (unsigned type : {2002u, 3008u})
      if (!call<int>(Exists, reinterpret_cast<void *>(manager),
                     next.model.data(), type,
                     static_cast<std::uint32_t *>(nullptr))) {
        error = type == 2002 ? "model MDL resource is missing"
                             : "model MDX resource is missing";
        return false;
      }
    next.table = ammunition_table();
    if (!next.table) {
      error = "installed ammunition table unavailable";
      return false;
    }
    // These labels are verified in the installed K1 GOG ammunitiontypes table.
    // Fetch model names from that engine table; never guess a mesh from row
    // alone.
    const char *labels[] = {"Blaster", "Ion", "Disruptor", "Sonic",
                            "Bowcaster"};
    for (unsigned row = 1; row <= 5; ++row) {
      std::string label;
      if (!table_entry(next.table, row, "label", label) ||
          label != labels[row - 1]) {
        error = "unsupported installed ammunition label";
        return false;
      }
      for (unsigned variant = 0; variant < 2; ++variant) {
        std::string model;
        if (!table_entry(next.table, row, variant ? "Model1" : "Model0",
                         model) ||
            !valid_name(model)) {
          error = "invalid installed ammunition model";
          return false;
        }
        next.ammo[next.count++] = {row, variant, ref(model)};
      }
    }
    return true;
  }
  int load(const Context &c, const Ref *replacement) override {
    using F = int(__attribute__((thiscall)) *)(void *, const void *,
                                               std::uint32_t, std::uint32_t);
    return reinterpret_cast<F>(original)(
        reinterpret_cast<void *>(c.object),
        replacement ? replacement->data()
                    : reinterpret_cast<void *>(c.original_pointer),
        c.flag1, c.flag2);
  }
} native;
class NativeSlotAccess final : public SlotAccess {
public:
  bool writable(Address slot, std::uint32_t &previous) override {
    DWORD old = 0;
    if (!VirtualProtect(reinterpret_cast<void *>(slot), sizeof(void *),
                        PAGE_READWRITE, &old))
      return false;
    previous = old;
    return true;
  }
  bool restore(Address slot, std::uint32_t protection) override {
    DWORD ignored = 0;
    return VirtualProtect(reinterpret_cast<void *>(slot), sizeof(void *),
                          protection, &ignored) != 0;
  }
  bool exchange(Address slot, Address expected, Address desired,
                Address &observed) override {
    observed = reinterpret_cast<Address>(InterlockedCompareExchangePointer(
        reinterpret_cast<void **>(slot), reinterpret_cast<void *>(desired),
        reinterpret_cast<void *>(expected)));
    return true;
  }
} slot_access;

} // namespace
bool bind_native(const std::string &sha, Address base, std::string &error) {
  unbind_native();
  if (native.patch.pending()) {
    error = "previous projectile slot could not be restored";
    return false;
  }
  if (sha != profile().sha || !base || base > UINT32_MAX - 0x400000) {
    error = "unsupported projectile executable image";
    service().bind(nullptr, error, sha);
    return false;
  }
  native.base = base;
  if (!native.guards(error)) {
    service().bind(nullptr, error, profile().name);
    return false;
  }
  native.original =
      reinterpret_cast<void *>(native.at(profile().sites[Load].va));
  // Publish the callable backend before the atomic slot becomes visible.
  service().bind(&native, "verified load boundary; impact/coverage unverified",
                 profile().name);
  bool installed = native.patch.install(
      slot_access, native.at(profile().projectile_vtable) + 0x78,
      reinterpret_cast<Address>(native.original),
      reinterpret_cast<Address>(&kp_projectile_entry), error);
  if (!installed) {
    if (native.patch.pending())
      service().suspend(error);
    else
      service().bind(nullptr, error, profile().name);
  }
  return installed;
}
void unbind_native() {
  if (native.patch.pending()) {
    std::string error;
    service().suspend("projectile slot cleanup in progress");
    if (!native.patch.remove(slot_access, error)) {
      service().suspend(error);
      return;
    }
  }
  service().bind(nullptr, "projectile binding inactive", "");
}
extern "C" __attribute__((force_align_arg_pointer)) int
kp_projectile_dispatch(const ProjectileRegisters *regs,
                       const std::uint32_t *sp) {
  Context c;
  c.object = regs->ecx;
  c.original_pointer = sp[1];
  c.flag1 = sp[2];
  c.flag2 = sp[3];
  if (!service().active())
    return native.load(c, nullptr);
  if (sp[0] == native.at(profile().return_address) &&
      native.ptr(c.object) == native.at(profile().projectile_vtable)) {
    c.receiver =
        native.read(reinterpret_cast<Address>(sp) + 0x9c, &c.source, 4) &&
        native.read(reinterpret_cast<Address>(sp) + 0x24, &c.target, 4) &&
        native.read(c.original_pointer, c.original.data(), 16);
    unsigned char row = 0, variant = 0;
    c.receiver = c.receiver &&
                 native.read(reinterpret_cast<Address>(sp) + 0x21, &row, 1) &&
                 native.read(reinterpret_cast<Address>(sp) + 0x22, &variant, 1);
    c.row = row;
    c.variant = variant;
  }
  return service().intercept(c);
}
#else
bool bind_native(const std::string &, Address, std::string &error) {
  error = "unsupported: projectile native adapter requires Windows i386";
  service().bind(nullptr, error, "");
  return false;
}
void unbind_native() {
  service().bind(nullptr, "projectile binding inactive", "");
}
#endif
} // namespace kp::api::projectiles
