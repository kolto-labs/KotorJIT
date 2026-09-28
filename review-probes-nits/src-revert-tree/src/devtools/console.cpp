#include "devtools/console.hpp"
extern "C" {
#include <lauxlib.h>
#include <lua.h>
#include <luajit.h>
#include <lualib.h>
}
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <unordered_set>
namespace kp::devtools {
namespace {
thread_local Console *running = nullptr;
std::atomic<Session> next_session{1};
constexpr std::size_t kOutcomeBytes = 262144;
std::size_t outcome_bytes(const Outcome &o) {
  std::size_t n = sizeof(Outcome) + o.error.code.size() + o.error.text.size();
  for (auto &v : o.values)
    n += sizeof(ReturnValue) + v.bytes.size() + v.opaque_type.size();
  return n;
}
ReturnValue typed_value(lua_State *L, int i, std::size_t &remaining) {
  ReturnValue v;
  switch (lua_type(L, i)) {
  case LUA_TNIL:
    break;
  case LUA_TBOOLEAN:
    v.type = ValueType::Boolean;
    v.boolean = lua_toboolean(L, i) != 0;
    break;
  case LUA_TNUMBER: {
    v.type = ValueType::Number;
    double n = lua_tonumber(L, i);
    if (std::isnan(n))
      v.number_kind = NumberKind::NaN;
    else if (std::isinf(n))
      v.number_kind =
          n > 0 ? NumberKind::PositiveInfinity : NumberKind::NegativeInfinity;
    else
      v.number = n;
    break;
  }
  case LUA_TSTRING: {
    v.type = ValueType::String;
    size_t n;
    const char *p = lua_tolstring(L, i, &n);
    v.original_bytes = n;
    auto keep = std::min({n, size_t(8192), remaining});
    v.bytes.assign(p, keep);
    v.truncated = keep < n;
    remaining -= keep;
    break;
  }
  default:
    v.type = ValueType::Opaque;
    v.opaque_type = luaL_typename(L, i);
    break;
  }
  return v;
}
std::string value(lua_State *L, int i) {
  switch (lua_type(L, i)) {
  case LUA_TNIL:
    return "nil";
  case LUA_TBOOLEAN:
    return lua_toboolean(L, i) ? "true" : "false";
  case LUA_TSTRING: {
    size_t n;
    const char *p = lua_tolstring(L, i, &n);
    return std::string(p, std::min(n, size_t(8192)));
  }
  case LUA_TNUMBER: {
    char b[64];
    std::snprintf(b, sizeof b, "%.17g", lua_tonumber(L, i));
    return b;
  }
  default: {
    char b[80];
    std::snprintf(b, sizeof b, "%s: %p", luaL_typename(L, i),
                  lua_topointer(L, i));
    return b;
  }
  }
}
int print(lua_State *L) {
  std::string s;
  for (int i = 1; i <= lua_gettop(L); ++i) {
    if (i > 1)
      s += '\t';
    // Match stock print's global tostring behavior, including metamethods.
    lua_getglobal(L, "tostring");
    lua_pushvalue(L, i);
    lua_call(L, 1, 1);
    size_t n;
    const char *p = lua_tolstring(L, -1, &n);
    if (!p)
      return luaL_error(L, "tostring must return a string to print");
    s.append(p, std::min(n, size_t(8192)));
    lua_pop(L, 1);
  }
  if (running)
    running->output("stdout", s + "\n");
  return 0;
}
int file_write(lua_State *L) {
  bool out = lua_rawequal(L, 1, lua_upvalueindex(2));
  bool err = lua_rawequal(L, 1, lua_upvalueindex(3));
  if (!out && !err) {
    lua_pushvalue(L, lua_upvalueindex(1));
    lua_insert(L, 1);
    lua_call(L, lua_gettop(L) - 1, LUA_MULTRET);
    return lua_gettop(L);
  }
  std::string s;
  for (int i = 2; i <= lua_gettop(L); ++i) {
    size_t n;
    const char *p = luaL_checklstring(L, i, &n);
    s.append(p, std::min(n, size_t(8192)));
  }
  if (running)
    running->output(err ? "stderr" : "stdout", s);
  lua_pushvalue(L, 1);
  return 1;
}
int write(lua_State *L) {
  int n = lua_gettop(L);
  lua_getglobal(L, "io");
  lua_getfield(L, -1, "output");
  lua_call(L, 0, 1);
  if (!lua_rawequal(L, -1, lua_upvalueindex(2))) {
    lua_settop(L, n);
    lua_pushvalue(L, lua_upvalueindex(1));
    lua_insert(L, 1);
    lua_call(L, n, LUA_MULTRET);
    return lua_gettop(L);
  }
  lua_settop(L, n);
  std::string s;
  for (int i = 1; i <= n; ++i) {
    size_t len;
    const char *p = luaL_checklstring(L, i, &len);
    s.append(p, std::min(len, size_t(8192)));
  }
  if (running)
    running->output("stdout", s);
  lua_pushvalue(L, lua_upvalueindex(2));
  return 1;
}
int traceback(lua_State *L) {
  const char *s = lua_tostring(L, 1);
  luaL_traceback(L, L, s ? s : "non-string error", 1);
  return 1;
}
void budget(lua_State *L, lua_Debug *) {
  if (running && running->interrupted())
    luaL_error(L, "console cancelled or instruction budget exhausted");
}
void replace(lua_State *L, int table, const char *key, lua_CFunction fn) {
  lua_getfield(L, table, key);
  lua_pushcfunction(L, fn);
  lua_setfield(L, table, key);
}
} // namespace
Console::Console() : session_(next_session.fetch_add(1)) {}
Console::~Console() {
  if (state_)
    lua_close(state_);
}
Console &console() {
  static Console c;
  return c;
}
Submission Console::submit_locked(Session session, std::string code) {
  Submission result{session_, 0, Reject::None};
  if (session != session_)
    result.rejection = Reject::StaleSession;
  else if (code.size() > 16384)
    result.rejection = Reject::SourceLimit;
  else if (queue_.size() >= 16)
    result.rejection = Reject::QueueFull;
  else {
    result.request = ++submitted_;
    queue_.push_back({result.request, std::move(code)});
    Outcome pending;
    pending.session = session_;
    pending.request = result.request;
    outcomes_.emplace(result.request, std::move(pending));
  }
  if (result.rejection != Reject::None)
    output_locked(
        "error",
        "Submission rejected: stale session, full queue or source limit.", 0);
  return result;
}
Request Console::submit(std::string code) {
  std::lock_guard lock(mutex_);
  return submit_locked(session_, std::move(code)).request;
}
Submission Console::submit(Session session, std::string code) {
  std::lock_guard lock(mutex_);
  return submit_locked(session, std::move(code));
}
Status Console::status() {
  std::lock_guard lock(mutex_);
  return {submitted_, completed_,     active_ != 0,  queue_.size(),
          session_,   line_sequence_, dropped_lines_};
}
Lookup Console::lookup_locked(Session session, Request request) {
  if (session != session_)
    return Lookup::StaleSession;
  if (outcomes_.count(request))
    return Lookup::Found;
  if (request >= epoch_first_ && request <= submitted_)
    return Lookup::Expired;
  return Lookup::Unavailable;
}
OutcomeLookup Console::outcome(Session session, Request request) {
  std::lock_guard lock(mutex_);
  OutcomeLookup result;
  result.status = lookup_locked(session, request);
  if (result.status == Lookup::Found)
    result.outcome = outcomes_.at(request);
  return result;
}
void Console::output_locked(std::string kind, std::string text,
                            Request request) {
  if (text.size() > 8192)
    text = text.substr(0, 8192) + " [truncated]";
  bytes_ += text.size();
  lines_.push_back(
      {std::move(kind), std::move(text), request, session_, ++line_sequence_});
  auto found = outcomes_.find(request);
  if (found != outcomes_.end() &&
      found->second.state == RequestState::Running) {
    if (!found->second.first_line)
      found->second.first_line = line_sequence_;
    found->second.last_line = line_sequence_;
  }
  while (lines_.size() > 512 || bytes_ > 262144) {
    bytes_ -= lines_.front().text.size();
    dropped_through_ = lines_.front().sequence;
    ++dropped_lines_;
    lines_.pop_front();
  }
}
void Console::output(std::string kind, std::string text) {
  std::lock_guard lock(mutex_);
  // Only output on the executing owner thread is attributed to its request.
  // Concurrent UI, rejection and diagnostic output must not borrow that ID.
  output_locked(std::move(kind), std::move(text),
                running == this ? active_ : 0);
}
std::vector<Line> Console::snapshot() {
  std::lock_guard lock(mutex_);
  return {lines_.begin(), lines_.end()};
}
OutputSnapshot Console::snapshot(Session session, std::uint64_t after) {
  std::lock_guard lock(mutex_);
  OutputSnapshot result;
  result.session = session_;
  if (session != session_) {
    result.status = Lookup::StaleSession;
    return result;
  }
  result.last_sequence = line_sequence_;
  result.dropped_lines = dropped_lines_;
  result.dropped_through = dropped_through_;
  for (auto &line : lines_)
    if (line.sequence > after)
      result.lines.push_back(line);
  return result;
}
void Console::terminal_locked(Outcome result) {
  auto &existing = outcomes_.at(result.request);
  result.first_line = existing.first_line;
  result.last_line = existing.last_line;
  existing = std::move(result);
  outcome_bytes_ += outcome_bytes(existing);
  terminal_order_.push_back(existing.request);
  // Legacy polling observes a contiguous terminal prefix, not the largest
  // terminal ID. The bounded outstanding set survives outcome eviction.
  Request earliest = queue_.empty() ? 0 : queue_.front().first;
  if (active_ && outcomes_.at(active_).state == RequestState::Running)
    earliest = earliest ? std::min(earliest, active_) : active_;
  completed_ =
      earliest ? (earliest == epoch_first_ ? 0 : earliest - 1) : submitted_;
  while (terminal_order_.size() > 128 || outcome_bytes_ > kOutcomeBytes) {
    auto id = terminal_order_.front();
    terminal_order_.pop_front();
    outcome_bytes_ -= outcome_bytes(outcomes_.at(id));
    outcomes_.erase(id);
  }
}
Cancellation Console::cancel(Session session, Request request) {
  std::lock_guard lock(mutex_);
  switch (lookup_locked(session, request)) {
  case Lookup::StaleSession:
    return Cancellation::StaleSession;
  case Lookup::Expired:
    return Cancellation::Expired;
  case Lookup::Unavailable:
    return Cancellation::Unavailable;
  case Lookup::Found:
    break;
  }
  auto &result = outcomes_.at(request);
  if (result.state == RequestState::Running) {
    cancelled_ = true;
    return Cancellation::Requested;
  }
  if (result.state != RequestState::Pending)
    return Cancellation::AlreadyTerminal;
  auto queued = std::find_if(queue_.begin(), queue_.end(),
                             [&](auto &q) { return q.first == request; });
  queue_.erase(queued);
  Outcome terminal = result;
  terminal.state = RequestState::Cancelled;
  terminal.error = {"cancelled", "Cancelled before execution", false};
  terminal_locked(std::move(terminal));
  return Cancellation::Cancelled;
}
void Console::cancel() {
  std::lock_guard lock(mutex_);
  if (active_)
    cancelled_ = true;
}
std::vector<std::string> Console::complete(const std::string &prefix) {
  std::lock_guard lock(mutex_);
  std::vector<std::string> r;
  for (auto &n : names_)
    if (n.rfind(prefix, 0) == 0 && r.size() < 64)
      r.push_back(n);
  return r;
}
bool Console::interrupted() {
  instructions_ += 1000;
  if (cancelled_.load()) {
    cancellation_observed_ = true;
    return true;
  }
  if (instructions_ >= 1000000) {
    budget_exhausted_ = true;
    return true;
  }
  return false;
}
void Console::reset() {
  // Caller guarantees engine ownership and no pump on the stack. Publish the
  // new session and detach state before lua_close invokes finalizers.
  lua_State *old = state_;
  state_ = nullptr;
  io_ref_ = -1;
  {
    std::lock_guard lock(mutex_);
    session_ = next_session.fetch_add(1);
    epoch_first_ = submitted_ + 1;
    completed_ = 0;
    active_ = 0;
    queue_.clear();
    outcomes_.clear();
    terminal_order_.clear();
    outcome_bytes_ = 0;
    names_.clear();
    lines_.clear();
    bytes_ = 0;
    dropped_lines_ = 0;
    dropped_through_ = 0;
    cancelled_ = false;
  }
  if (old)
    lua_close(old);
}
void Console::pump(const std::function<void(lua_State *)> &init) {
  static thread_local bool busy = false;
  if (busy)
    return;
  busy = true;
  if (!state_) {
    state_ = luaL_newstate();
    if (state_) {
      luaL_openlibs(state_);
      if (init)
        init(state_);
      lua_getglobal(state_, "io");
      io_ref_ = luaL_ref(state_, LUA_REGISTRYINDEX);
      index();
    }
  }
  std::string code;
  Session session;
  Request request;
  {
    std::lock_guard lock(mutex_);
    if (queue_.empty()) {
      busy = false;
      return;
    }
    request = queue_.front().first;
    code = std::move(queue_.front().second);
    queue_.pop_front();
    // Reset before publishing Running: cancel cannot be erased after observing
    // the active request, and a finished request cannot poison its successor.
    cancelled_ = false;
    instructions_ = 0;
    budget_exhausted_ = false;
    cancellation_observed_ = false;
    active_ = request;
    session = session_;
    outcomes_.at(request).state = RequestState::Running;
  }
  running = this;
  Outcome result;
  if (state_) {
    result = execute(code);
    index();
  } else {
    result.state = RequestState::Failed;
    result.error = {"allocation", "Cannot allocate Lua state", false};
    output("error", result.error.text);
  }
  running = nullptr;
  {
    std::lock_guard lock(mutex_);
    result.session = session;
    result.request = request;
    terminal_locked(std::move(result));
    active_ = 0;
    cancelled_ = false;
  }
  busy = false;
}
Outcome Console::execute(const std::string &code) {
  Outcome result;
  auto *L = state_;
  const int base = lua_gettop(L);
  output("input", "> " + code);
  // Routing is scoped to this execution, then exact previous globals restored.
  replace(L, LUA_GLOBALSINDEX, "print", print);
  const int oldprint = lua_gettop(L);
  lua_rawgeti(L, LUA_REGISTRYINDEX, io_ref_);
  const int io = lua_gettop(L);
  lua_getfield(L, io, "write");
  const int oldwrite = lua_gettop(L);
  lua_pushvalue(L, oldwrite);
  lua_getfield(L, io, "stdout");
  lua_pushcclosure(L, write, 2);
  lua_setfield(L, io, "write");
  luaL_getmetatable(L, LUA_FILEHANDLE);
  const int filemeta = lua_gettop(L);
  lua_getfield(L, filemeta, "write");
  const int oldfilewrite = lua_gettop(L);
  lua_pushvalue(L, oldfilewrite);
  lua_getfield(L, io, "stdout");
  lua_getfield(L, io, "stderr");
  lua_pushcclosure(L, file_write, 3);
  lua_setfield(L, filemeta, "write");
  lua_pushcfunction(L, traceback);
  const int handler = lua_gettop(L);
  std::string expr = "return " + code;
  int rc = luaL_loadbuffer(L, expr.data(), expr.size(), "=devtools");
  if (rc) {
    lua_pop(L, 1);
    rc = luaL_loadbuffer(L, code.data(), code.size(), "=devtools");
  }
  const bool syntax_error = rc != 0;
  // Disable JIT on the whole state and flush traces: compiled loops bypass
  // hooks.
  luaJIT_setmode(L, 0, LUAJIT_MODE_ENGINE | LUAJIT_MODE_OFF);
  luaJIT_setmode(L, 0, LUAJIT_MODE_ENGINE | LUAJIT_MODE_FLUSH);
  lua_sethook(L, budget, LUA_MASKCOUNT, 1000);
  if (!rc)
    rc = lua_pcall(L, 0, LUA_MULTRET, handler);
  lua_sethook(L, nullptr, 0, 0);
  if (rc) {
    result.state =
        cancellation_observed_ ? RequestState::Cancelled : RequestState::Failed;
    result.error.code = syntax_error             ? "lua_syntax"
                        : cancellation_observed_ ? "cancelled"
                        : budget_exhausted_      ? "instruction_budget"
                                                 : "lua_runtime";
    result.error.text = value(L, -1);
    if (lua_type(L, -1) == LUA_TSTRING) {
      size_t length;
      lua_tolstring(L, -1, &length);
      result.error.truncated = length > 8192;
    }
    output("error", result.error.text);
  } else {
    result.state = RequestState::Succeeded;
    result.return_count = lua_gettop(L) - handler;
    result.returns_truncated = result.return_count > 64;
    std::size_t remaining = 32768;
    for (int i = handler + 1; i <= lua_gettop(L) && result.values.size() < 64;
         ++i) {
      auto typed = typed_value(L, i, remaining);
      result.returns_truncated = result.returns_truncated || typed.truncated;
      result.values.push_back(std::move(typed));
    }
    int n = lua_gettop(L) - handler;
    if (!n)
      output("result", "ok (no return values)");
    for (int i = handler + 1; i <= lua_gettop(L); ++i)
      output("result", std::string(luaL_typename(L, i)) + ": " + value(L, i));
  }
  lua_pushvalue(L, oldprint);
  lua_setglobal(L, "print");
  lua_pushvalue(L, oldwrite);
  lua_setfield(L, io, "write");
  lua_pushvalue(L, oldfilewrite);
  lua_setfield(L, filemeta, "write");
  lua_settop(L, base);
  return result;
}
void Console::index() {
  std::vector<std::string> names;
  std::unordered_set<const void *> visited;
  unsigned inspected = 0;
  auto *L = state_;
  int base = lua_gettop(L);
  auto walk = [&](auto &&self, int t, std::string prefix, int depth) -> void {
    if (!visited.insert(lua_topointer(L, t)).second)
      return;
    unsigned table_inspected = 0;
    lua_pushnil(L);
    while (lua_next(L, t) != 0) {
      ++inspected;
      ++table_inspected;
      if (lua_type(L, -2) == LUA_TSTRING) {
        std::string key = lua_tostring(L, -2);
        if (key.size() < 100 &&
            key.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQR"
                                  "STUVWXYZ0123456789_") == std::string::npos) {
          auto name = prefix + key;
          names.push_back(name);
          if (depth < 2 && key != "_G" && key != "package" &&
              lua_istable(L, -1) && names.size() < 4096)
            self(self, lua_gettop(L), name + ".", depth + 1);
        }
      }
      lua_pop(L, 1);
      if (names.size() >= 4096 || inspected >= 16384 ||
          table_inspected >= 256) {
        lua_pop(L, 1);
        break;
      }
    }
  };
  walk(walk, LUA_GLOBALSINDEX, "", 0);
  lua_settop(L, base);
  std::sort(names.begin(), names.end());
  names.erase(std::unique(names.begin(), names.end()), names.end());
  std::lock_guard lock(mutex_);
  names_ = std::move(names);
}
} // namespace kp::devtools
