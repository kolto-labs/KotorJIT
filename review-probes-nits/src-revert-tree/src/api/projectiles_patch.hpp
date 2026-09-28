#pragma once
#include <cstdint>
#include <string>
namespace kp::api::projectiles {
// Data-slot transaction. Calls are serialized by runtime install/shutdown.
// A failed exchange must guarantee that it did not write the slot.
struct SlotAccess {
  virtual ~SlotAccess() = default;
  virtual bool writable(std::uintptr_t slot, std::uint32_t &previous) = 0;
  virtual bool restore(std::uintptr_t slot, std::uint32_t protection) = 0;
  virtual bool exchange(std::uintptr_t slot, std::uintptr_t expected,
                        std::uintptr_t desired, std::uintptr_t &observed) = 0;
};
class SlotPatch {
public:
  bool pending() const { return slot_ != 0; }
  bool owns_slot() const { return owned_; }
  bool protection_pending() const { return protection_pending_; }
  bool install(SlotAccess &io, std::uintptr_t slot, std::uintptr_t original,
               std::uintptr_t replacement, std::string &error) {
    if (pending()) {
      error = "previous slot transaction requires cleanup";
      return false;
    }
    std::uint32_t protection;
    if (!io.writable(slot, protection)) {
      error = "slot write protection failed";
      return false;
    }
    slot_ = slot;
    original_ = original;
    replacement_ = replacement;
    protection_ = protection;
    protection_pending_ = true;
    std::uintptr_t observed = 0;
    bool exchanged = io.exchange(slot_, original_, replacement_, observed);
    owned_ = exchanged && observed == original_;
    const char *failure = !exchanged ? "slot exchange failed"
                          : !owned_  ? "slot changed before installation"
                                     : nullptr;
    if (!io.restore(slot_, protection_)) {
      error = failure
                  ? std::string(failure) + "; protection restoration pending"
                  : "installed slot protection restoration pending";
      return false;
    }
    protection_pending_ = false;
    if (!owned_) {
      clear();
      error = failure;
      return false;
    }
    return true;
  }
  bool remove(SlotAccess &io, std::string &error) {
    if (!pending())
      return true;
    std::uint32_t ignored;
    if (!io.writable(slot_, ignored)) {
      error = "slot cleanup write protection failed; ownership retained";
      return false;
    }
    protection_pending_ = true;
    std::uintptr_t observed = 0;
    if (owned_ && !io.exchange(slot_, replacement_, original_, observed)) {
      if (io.restore(slot_, protection_))
        protection_pending_ = false;
      error = "slot cleanup exchange failed; ownership retained";
      return false;
    }
    // A changed owner is left alone. In either case our value is no longer in
    // the slot. Do not forget protection bookkeeping until restoration works.
    const bool changed_owner =
        owned_ && observed != replacement_ && observed != original_;
    owned_ = false;
    if (!io.restore(slot_, protection_)) {
      error = changed_owner
                  ? "slot owner changed; protection restoration pending"
                  : "slot removed; protection restoration pending";
      return false;
    }
    clear();
    if (changed_owner)
      error = "slot owner changed; foreign value preserved";
    return true;
  }

private:
  void clear() {
    slot_ = original_ = replacement_ = 0;
    protection_ = 0;
    owned_ = protection_pending_ = false;
  }
  std::uintptr_t slot_ = 0, original_ = 0, replacement_ = 0;
  std::uint32_t protection_ = 0;
  bool owned_ = false, protection_pending_ = false;
};
} // namespace kp::api::projectiles
