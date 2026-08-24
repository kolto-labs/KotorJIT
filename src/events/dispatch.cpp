#include "events/contract.hpp"

namespace kp::events {

bool always_claimed_by_first(const EventContract& ev) {
    // Nothing to convert means nothing can fail to convert, so the first script
    // that defines the callback claims it no matter what it returns.
    return ev.results.empty();
}

}  // namespace kp::events
