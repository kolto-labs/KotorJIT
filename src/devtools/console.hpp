#pragma once
#include <atomic>
#include <cstdint>
#include <deque>
#include <functional>
#include <mutex>
#include <string>
#include <vector>
struct lua_State;
namespace kp::devtools {
struct Line {
  std::string kind, text;
  std::uint64_t request = 0;
};
struct Status {
  std::uint64_t submitted, completed;
  bool running;
  std::size_t queued;
};
// submit/snapshot/complete/cancel are thread safe. pump/reset belong
// exclusively to the established engine thread. No renderer may touch the Lua
// state.
class Console {
public:
  ~Console();
  std::uint64_t submit(std::string code);
  Status status();
  void pump(const std::function<void(lua_State *)> &init = {});
  void reset();
  void cancel() { cancelled_.store(true); }
  std::vector<Line> snapshot();
  std::vector<std::string> complete(const std::string &prefix);
  void output(std::string kind, std::string text);
  bool interrupted();

private:
  void execute(const std::string &);
  void index();
  lua_State *state_ = nullptr;
  int io_ref_ = -1;
  std::mutex mutex_;
  std::deque<std::pair<std::uint64_t, std::string>> queue_;
  std::uint64_t submitted_ = 0, completed_ = 0;
  std::atomic<std::uint64_t> active_{0};
  std::deque<Line> lines_;
  std::vector<std::string> names_;
  std::atomic<bool> cancelled_{false};
  unsigned instructions_ = 0;
  std::size_t bytes_ = 0;
};
Console &console();
void overlay_tick(); // installation from engine pump; never executes Lua
void overlay_shutdown();
bool overlay_open();
unsigned long overlay_input_calls();
} // namespace kp::devtools
