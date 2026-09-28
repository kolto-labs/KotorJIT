#pragma once
#include "devtools/console.hpp"
#include "harness/json.hpp"
namespace kp::harness::console_protocol {
// Lossless helpers are public for transport contract tests, not Lua evaluation.
Json decimal(std::uint64_t value);
Json bytes(const std::string &value);
Json outcome(const devtools::Outcome &value);
const std::string &runtime_instance();
// false denotes malformed wire input. Service refusals are explicit result
// states.
bool dispatch(devtools::Console &, const Json &request,
              const std::string &runtime, bool open, std::uint64_t input_calls,
              Json &result, std::string &error);
} // namespace kp::harness::console_protocol
