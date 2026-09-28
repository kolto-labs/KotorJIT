#include "events/contract.hpp"

namespace kp::events {

bool always_claimed_by_first(const EventContract& ev) {
    // Nothing to convert means nothing can fail to convert, so the first script
    // that defines the callback claims it no matter what it returns.
    return ev.results.empty();
}

BlockVerdict blocking_verdict(const EventContract& ev, const Outcome& outcome) {
    BlockVerdict v;
    if (!outcome.claimed || outcome.bool_result) return v;

    v.skip_original = true;
    switch (ev.engine_return) {
    case EngineReturn::ReportSuccess: v.engine_result = 1; break;
    case EngineReturn::ReportFailure: v.engine_result = 0; break;
    case EngineReturn::Passthrough:
        v.skip_original = false;
        break;
    }
    return v;
}

}  // namespace kp::events
