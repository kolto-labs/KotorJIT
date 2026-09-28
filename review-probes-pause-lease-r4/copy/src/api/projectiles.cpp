#include "api/projectiles.hpp"
#include <algorithm>
namespace kp::api::projectiles {
Service &service() {
  static Service s;
  return s;
}
std::string text(const Ref &r) {
  return std::string(r.begin(), std::find(r.begin(), r.end(), '\0'));
}
bool valid_name(const std::string &s) {
  return !s.empty() && s.size() <= 16 &&
         std::all_of(s.begin(), s.end(), [](unsigned char c) {
           return (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
                  (c >= '0' && c <= '9') || c == '_';
         });
}
void Service::bind(Backend *b, std::string reason, std::string build) {
  std::lock_guard lock(mutex_);
  auto epoch = status_.epoch + 1;
  backend_ = b;
  config_ = {};
  status_ = {};
  status_.epoch = epoch;
  status_.supported = b != nullptr;
  status_.reason = std::move(reason);
  status_.build = std::move(build);
  start_ = size_ = 0;
}
bool Service::configure(const std::string &model, std::string &error) {
  if (!valid_name(model)) {
    error = "model must be a 1–16 character resource name (letters, digits, "
            "underscore)";
    return false;
  }
  Backend *b;
  std::uint64_t epoch;
  bool supported;
  {
    std::lock_guard lock(mutex_);
    b = backend_;
    epoch = status_.epoch;
    supported = status_.supported;
  }
  if (!b || !supported) {
    error = "unsupported: no verified projectile binding";
    return false;
  }
  Config next;
  if (!b->prepare(model, next, error))
    return false;
  if (!next.count || next.count > next.ammo.size()) {
    error = "no verified installed ammunition entries";
    return false;
  }
  std::lock_guard lock(mutex_);
  if (!status_.supported || b != backend_ || epoch != status_.epoch) {
    error = "projectile binding changed during configuration";
    return false;
  }
  next.version = config_.version + 1;
  next.enabled = next.observing = true;
  config_ = next;
  return true;
}
bool Service::observe(bool on, std::string &error) {
  std::lock_guard lock(mutex_);
  if (!backend_ || !status_.supported) {
    error = "unsupported: no verified projectile binding";
    return false;
  }
  config_.observing = on;
  ++config_.version;
  return true;
}
void Service::disable() {
  std::lock_guard lock(mutex_);
  config_.enabled = false;
  ++config_.version;
}
void Service::suspend(const std::string &reason) {
  std::lock_guard lock(mutex_);
  config_.enabled = config_.observing = false;
  ++config_.version;
  status_.supported = false;
  status_.reason = reason;
}
bool Service::active() const {
  std::lock_guard lock(mutex_);
  return config_.observing || config_.enabled;
}
Status Service::status() const {
  std::lock_guard lock(mutex_);
  auto s = status_;
  s.observing = config_.observing;
  s.enabled = config_.enabled;
  s.version = config_.version;
  s.model = config_.model;
  return s;
}
std::vector<Record> Service::records() const {
  std::lock_guard lock(mutex_);
  std::vector<Record> out;
  out.reserve(size_);
  for (unsigned i = 0; i < size_; ++i)
    out.push_back(records_[(start_ + i) % records_.size()]);
  return out;
}
int Service::intercept(const Context &c) {
  Backend *b;
  Config cfg;
  std::uint64_t epoch;
  {
    std::lock_guard lock(mutex_);
    b = backend_;
    cfg = config_;
    epoch = status_.epoch;
  }
  if (!b)
    return 0; // Binding lifetime is owned by quiescent runtime
              // install/uninstall.
  if (!cfg.observing && !cfg.enabled)
    return b->load(c, nullptr);
  bool replace = false;
  const char *reason = "other_callsite";
  std::uint32_t pc = 0;
  if (c.receiver) {
    if (!b->current_pc(pc))
      reason = "source_unresolved";
    else if (pc != c.source)
      reason = "non_pc";
    else if (!cfg.enabled)
      reason = "stock_observation";
    else if (cfg.table != b->ammunition_table())
      reason = "ammunition_table_changed";
    else {
      reason = "unclassified";
      for (unsigned i = 0; i < cfg.count; ++i) {
        const auto &a = cfg.ammo[i];
        if (a.row == c.row && a.variant == c.variant && a.model == c.original) {
          replace = true;
          reason = "selected";
          break;
        }
      }
    }
  }
  // The copied configuration owns this synchronous call's chosen resource.
  // A failure is returned unchanged; never retry a partially initialized
  // wrapper.
  int result = b->load(c, replace ? &cfg.model : nullptr);
  Record r;
  r.epoch = epoch;
  r.version = cfg.version;
  r.source = c.source;
  r.target = c.target;
  r.row = c.row;
  r.variant = c.variant;
  r.original = c.original;
  r.selected = replace ? cfg.model : c.original;
  r.replaced = replace;
  r.load_ok = result != 0;
  r.reason = reason;
  {
    std::lock_guard lock(mutex_);
    if (epoch == status_.epoch) {
      r.sequence = ++status_.observed;
      if (replace)
        ++status_.replaced;
      if (size_ == records_.size()) {
        start_ = (start_ + 1) % records_.size();
        --size_;
        ++status_.dropped;
      }
      records_[(start_ + size_) % records_.size()] = std::move(r);
      ++size_;
    }
  }
  return result;
}
} // namespace kp::api::projectiles
