#pragma once
#include <atomic>
#include <cstdint>
#include <deque>
#include <functional>
#include <map>
#include <mutex>
#include <string>
#include <vector>
struct lua_State;
namespace kp::devtools {
using Session = std::uint64_t;
using Request = std::uint64_t;
enum class RequestState { Pending, Running, Succeeded, Failed, Cancelled };
enum class Lookup { Found, StaleSession, Expired, Unavailable };
enum class Reject { None, StaleSession, QueueFull, SourceLimit };
enum class Cancellation {
  Cancelled,
  Requested,
  AlreadyTerminal,
  StaleSession,
  Expired,
  Unavailable
};
enum class ValueType { Nil, Boolean, Number, String, Opaque };
enum class NumberKind { Finite, NaN, PositiveInfinity, NegativeInfinity };
struct ReturnValue {
  ValueType type = ValueType::Nil;
  bool boolean = false;
  double number = 0;
  NumberKind number_kind = NumberKind::Finite;
  // String values are raw bytes, never assumed UTF-8; opaque values carry only
  // a Lua type name. No pointer is a portable object reference.
  std::string bytes;
  std::string opaque_type;
  std::size_t original_bytes = 0;
  bool truncated = false;
  bool inspection_available = false;
};
struct Error {
  std::string code, text;
  bool truncated = false;
};
struct Outcome {
  Session session = 0;
  Request request = 0;
  RequestState state = RequestState::Pending;
  std::vector<ReturnValue> values;
  std::size_t return_count = 0;
  bool returns_truncated = false;
  Error error;
  std::uint64_t first_line = 0, last_line = 0;
};
struct OutcomeLookup {
  Lookup status = Lookup::Unavailable;
  Outcome outcome;
};
struct Submission {
  Session session = 0;
  Request request = 0;
  Reject rejection = Reject::None;
};
struct Line {
  std::string kind, text;
  Request request = 0;
  Session session = 0;
  std::uint64_t sequence = 0;
};
struct Status {
  Request submitted, completed;
  bool running;
  std::size_t queued;
  Session session;
  std::uint64_t last_line, dropped_lines;
};
struct OutputSnapshot {
  Lookup status = Lookup::Found;
  Session session = 0;
  std::uint64_t last_sequence = 0, dropped_lines = 0, dropped_through = 0;
  std::vector<Line> lines;
};
// All observation/submission/cancellation APIs synchronize through mutex_.
// pump/reset belong exclusively to the established engine owner thread.
class Console {
public:
  Console();
  ~Console();
  Request submit(std::string code);
  Submission submit(Session session, std::string code);
  Status status();
  OutcomeLookup outcome(Session session, Request request);
  OutputSnapshot snapshot(Session session, std::uint64_t after_sequence);
  std::vector<Line> snapshot();
  Cancellation cancel(Session session, Request request);
  void
  cancel(); // legacy: request cancellation of the currently running command
  void pump(const std::function<void(lua_State *)> &init = {});
  void reset(); // owner thread only, never concurrent/reentrant with pump
  std::vector<std::string> complete(const std::string &prefix);
  void output(std::string kind, std::string text);
  bool interrupted();

private:
  Outcome execute(const std::string &);
  void index();
  Submission submit_locked(Session session, std::string code);
  void output_locked(std::string kind, std::string text, Request request);
  void terminal_locked(Outcome outcome);
  Lookup lookup_locked(Session session, Request request);
  lua_State *state_ = nullptr;
  int io_ref_ = -1;
  std::mutex mutex_;
  std::mutex pump_mutex_;
  Session session_;
  Request epoch_first_ = 1;
  std::deque<std::pair<Request, std::string>> queue_;
  Request submitted_ = 0, completed_ = 0, active_ = 0;
  std::map<Request, Outcome> outcomes_;
  std::deque<Request> terminal_order_;
  std::size_t outcome_bytes_ = 0;
  std::deque<Line> lines_;
  std::vector<std::string> names_;
  std::atomic<bool> cancelled_{false};
  bool budget_exhausted_ = false, cancellation_observed_ = false;
  unsigned instructions_ = 0;
  std::size_t bytes_ = 0;
  std::uint64_t line_sequence_ = 0, dropped_lines_ = 0, dropped_through_ = 0;
};
Console &console();
void overlay_tick();
void overlay_shutdown();
bool overlay_open();
unsigned long overlay_input_calls();
} // namespace kp::devtools
