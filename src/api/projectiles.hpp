#pragma once
#include <array>
#include <cstdint>
#include <mutex>
#include <string>
#include <vector>
struct lua_State;
namespace kp::api::projectiles {
using Ref = std::array<char, 16>;
using Address = std::uintptr_t;
struct Ammo {
  unsigned row = 0, variant = 0;
  Ref model{};
};
struct Config {
  bool observing = false, enabled = false;
  std::uint64_t version = 0;
  Ref model{};
  std::array<Ammo, 10> ammo{};
  unsigned count = 0;
  Address table = 0;
};
struct Context {
  Address object = 0, original_pointer = 0;
  std::uint32_t source = 0, target = 0, flag1 = 0, flag2 = 0;
  unsigned row = 0, variant = 0;
  Ref original{};
  bool receiver = false;
};
struct Record {
  std::uint64_t sequence = 0, epoch = 0, version = 0;
  std::uint32_t source = 0, target = 0;
  unsigned row = 0, variant = 0;
  Ref original{}, selected{};
  bool replaced = false, load_ok = false;
  const char *reason = "";
};
struct Status {
  bool supported = false, observing = false, enabled = false;
  std::uint64_t epoch = 0, version = 0, observed = 0, replaced = 0, dropped = 0;
  Ref model{};
  std::string reason, build;
};
struct Backend {
  virtual ~Backend() = default;
  virtual bool prepare(const std::string &, Config &, std::string &) = 0;
  virtual bool current_pc(std::uint32_t &) = 0;
  virtual Address ammunition_table() = 0;
  virtual int load(const Context &, const Ref *replacement) = 0;
};
class Service {
public:
  void bind(Backend *, std::string reason, std::string build);
  bool configure(const std::string &, std::string &);
  bool observe(bool, std::string &);
  void disable();
  void suspend(const std::string &reason);
  bool active() const;
  Status status() const;
  std::vector<Record> records() const;
  int intercept(const Context &);

private:
  mutable std::mutex mutex_;
  Backend *backend_ = nullptr;
  Config config_{};
  Status status_{};
  std::array<Record, 128> records_{};
  unsigned start_ = 0, size_ = 0;
};
Service &service();
bool valid_name(const std::string &);
std::string text(const Ref &);
bool bind_native(const std::string &verified_sha, Address base,
                 std::string &error);
void unbind_native();
void register_all(lua_State *);
} // namespace kp::api::projectiles
