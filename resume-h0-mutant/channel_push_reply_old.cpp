// Private H0 red control.  This deliberately restores the pre-fix admission
// predicate while retaining the production queue ceiling and mutex behavior.
// It is outside the worktree and is never part of the product source.
#include "harness/channel.hpp"

#include <cstddef>
#include <mutex>
#include <utility>

namespace kp::harness {

void Channel::push_reply(std::uint64_t client, std::string line) {
    // Old behavior: condemned generations were indistinguishable from the
    // current generation, so a later stream/deferred reply could leak.
    if (client == 0 || client != current_client()) return;
    std::lock_guard<std::mutex> lock(mutex_);
    constexpr std::size_t kMaxQueuedReplies = 4096;
    constexpr std::size_t kMaxQueuedBytes = 8u << 20;
    if (replies_.size() >= kMaxQueuedReplies || reply_bytes_ + line.size() > kMaxQueuedBytes) {
        overflow_.store(true, std::memory_order_release);
        return;
    }
    reply_bytes_ += line.size();
    replies_.push_back({client, std::move(line)});
}

}  // namespace kp::harness
