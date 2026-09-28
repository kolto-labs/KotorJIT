#pragma once

#include <chrono>

namespace kp::harness::pause::snippet {

inline constexpr std::chrono::seconds kArmedTimeout{60};

inline bool armed_expired(std::chrono::steady_clock::time_point now,
                          std::chrono::steady_clock::time_point armed_at) {
    return armed_at != std::chrono::steady_clock::time_point{} &&
           now - armed_at >= kArmedTimeout;
}

}
