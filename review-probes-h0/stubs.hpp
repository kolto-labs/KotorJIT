#pragma once
#include <atomic>
#include <condition_variable>
#include <functional>
#include <mutex>

namespace probe {
extern std::atomic<int> submit_plain;
extern std::atomic<int> submit_session;
extern std::function<void()> on_submit;
extern std::atomic<int> connected;
extern std::atomic<int> disconnected;
extern std::atomic<int> doomed_logs;
extern std::atomic<bool> park_enabled;
extern std::atomic<bool> parked;
extern bool verbose;
void release_park();
void arm_park();
}  // namespace probe
