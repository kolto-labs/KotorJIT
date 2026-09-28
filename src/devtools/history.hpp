#pragma once
#include <optional>
#include <string>
#include <vector>

namespace kp::devtools {
// UI-independent command history. Navigation borrows the edit buffer only on
// entry; returning past the newest command restores that exact draft.
class History {
public:
  std::optional<std::string> navigate(bool older, const std::string &current) {
    if (entries_.empty())
      return std::nullopt;
    if (older) {
      if (position_ < 0) {
        draft_ = current;
        position_ = static_cast<int>(entries_.size()) - 1;
      } else if (position_ > 0)
        --position_;
    } else {
      if (position_ < 0)
        return std::nullopt;
      if (++position_ == static_cast<int>(entries_.size())) {
        position_ = -1;
        return draft_;
      }
    }
    return entries_[position_];
  }

  void submitted(const std::string &command, bool accepted) {
    if (!accepted)
      return;
    entries_.push_back(command);
    if (entries_.size() > 100)
      entries_.erase(entries_.begin());
    position_ = -1;
    draft_.clear();
  }

private:
  std::vector<std::string> entries_;
  std::string draft_;
  int position_ = -1;
};
} // namespace kp::devtools
