#include "devtools/console.hpp"
#include "devtools/history.hpp"
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <thread>
extern "C" {
#include <lauxlib.h>
#include <lua.h>
}
using kp::devtools::Console;
void require(bool condition, const char *message) {
  if (!condition) {
    std::fprintf(stderr, "FAIL: %s\n", message);
    std::exit(1);
  }
}
bool contains(Console &c, const std::string &kind, const std::string &text) {
  for (auto &l : c.snapshot())
    if (l.request == c.status().completed && l.kind == kind &&
        l.text.find(text) != std::string::npos)
      return true;
  return false;
}
void run(Console &c, const std::string &code, bool expect_error = false) {
  auto id = c.submit(code);
  require(id != 0, "accepted");
  c.pump();
  require(c.status().completed == id, "completed request");
  bool error = false;
  for (auto &l : c.snapshot())
    if (l.request == id && l.kind == "error")
      error = true;
  require(error == expect_error, "request error expectation");
}
using namespace kp::devtools;
Outcome evaluate(Console &c, const std::string &code) {
  auto session = c.status().session;
  auto receipt = c.submit(session, code);
  require(receipt.rejection == Reject::None && receipt.request != 0,
          "typed submit accepted");
  auto pending = c.outcome(session, receipt.request);
  require(pending.status == Lookup::Found &&
              pending.outcome.state == RequestState::Pending,
          "pending outcome");
  c.pump();
  auto terminal = c.outcome(session, receipt.request);
  require(terminal.status == Lookup::Found, "terminal retained");
  return terminal.outcome;
}
std::mutex gate_mutex;
std::condition_variable gate_condition;
bool gate_entered = false, gate_released = false;
int gate(lua_State *) {
  std::unique_lock lock(gate_mutex);
  gate_entered = true;
  gate_condition.notify_all();
  require(gate_condition.wait_for(lock, std::chrono::seconds(3),
                                  [] { return gate_released; }),
          "cancel test gate timeout");
  return 0;
}
void typed_tests() {
  Console c;
  auto epoch = c.status().session;
  auto a = c.submit(epoch, "shared = 40");
  auto b = c.submit(epoch, "shared = shared + 2");
  auto read = c.submit(epoch, "shared");
  require(a.request < b.request && b.request < read.request,
          "interleaved clients accepted in order");
  c.pump();
  c.pump();
  c.pump();
  auto shared = c.outcome(epoch, read.request).outcome;
  require(shared.state == RequestState::Succeeded &&
              shared.values.at(0).number == 42,
          "clients share persistent interpreter");
  auto tuple = evaluate(c, "nil,false,1.25,0/0,1/0,-1/"
                           "0,string.char(65,0,255),{},function()end,io.stdout,"
                           "coroutine.create(function()end)");
  require(tuple.state == RequestState::Succeeded && tuple.return_count == 11 &&
              tuple.values.size() == 11,
          "typed tuple count");
  require(tuple.values[0].type == ValueType::Nil &&
              tuple.values[1].type == ValueType::Boolean &&
              !tuple.values[1].boolean,
          "typed nil and false positions");
  require(tuple.values[2].number == 1.25 &&
              tuple.values[2].number_kind == NumberKind::Finite,
          "finite number");
  require(tuple.values[3].number_kind == NumberKind::NaN &&
              tuple.values[4].number_kind == NumberKind::PositiveInfinity &&
              tuple.values[5].number_kind == NumberKind::NegativeInfinity,
          "nonfinite descriptors");
  require(tuple.values[6].bytes == std::string("A\0\xff", 3) &&
              tuple.values[6].original_bytes == 3,
          "binary string preserved");
  for (unsigned i = 7; i < 11; ++i)
    require(tuple.values[i].type == ValueType::Opaque &&
                !tuple.values[i].inspection_available &&
                tuple.values[i].bytes.empty() &&
                !tuple.values[i].opaque_type.empty(),
            "opaque type descriptor without portable pointer");
  auto empty = evaluate(c, "local local_only=1");
  require(empty.values.empty() && empty.return_count == 0,
          "no return distinct from nil");
  auto longstring = evaluate(c, "string.rep('x',9000)");
  require(longstring.values[0].bytes.size() == 8192 &&
              longstring.values[0].original_bytes == 9000 &&
              longstring.values[0].truncated,
          "per-string truncation explicit");
  auto many =
      evaluate(c, "local t={} for i=1,80 do t[i]=i end return unpack(t)");
  require(many.return_count == 80 && many.values.size() == 64 &&
              many.returns_truncated,
          "bounded return tuple explicit");
  auto syntax = evaluate(c, "local ???");
  require(syntax.state == RequestState::Failed &&
              syntax.error.code == "lua_syntax",
          "structured syntax failure");
  auto runtime = evaluate(c, "error('typed failure')");
  require(runtime.state == RequestState::Failed &&
              runtime.error.code == "lua_runtime" &&
              runtime.error.text.find("stack traceback:") != std::string::npos,
          "structured runtime traceback");
  auto budget = evaluate(c, "while true do end");
  require(budget.state == RequestState::Failed &&
              budget.error.code == "instruction_budget",
          "budget separate from cancellation");
  auto recovery = evaluate(c, "42");
  require(recovery.state == RequestState::Succeeded &&
              recovery.values[0].number == 42,
          "structured recovery");
  for (int i = 0; i < 700; ++i)
    c.output("noise", std::string(1000, 'x'));
  auto output = c.snapshot(epoch, 0);
  require(output.dropped_lines > 0 && output.dropped_through > 0 &&
              output.lines.front().sequence > output.dropped_through,
          "explicit dropped output cursor");
  require(c.outcome(epoch, recovery.request).outcome.state ==
              RequestState::Succeeded,
          "outcome survives output eviction");
  require(c.snapshot(epoch, output.last_sequence).lines.empty(),
          "cursor suppresses previously delivered output");
  for (int i = 0; i < 130; ++i)
    evaluate(c, "1");
  require(c.outcome(epoch, recovery.request).status == Lookup::Expired,
          "explicit outcome count eviction");
  auto byte_victim = evaluate(c, "1");
  for (int i = 0; i < 12; ++i)
    evaluate(c, "string.rep('a',8192),string.rep('b',8192),string.rep('c',8192)"
                ",string.rep('d',8192)");
  require(c.outcome(epoch, byte_victim.request).status == Lookup::Expired,
          "outcome byte budget independently evicts");
  auto cancelled = c.submit(epoch, "shared=999");
  auto later = c.submit(epoch, "shared");
  require(c.cancel(epoch, cancelled.request) == Cancellation::Cancelled,
          "exact queued cancellation confirmed");
  require(c.outcome(epoch, cancelled.request).outcome.state ==
              RequestState::Cancelled,
          "queued terminal cancelled");
  c.pump();
  require(c.outcome(epoch, later.request).outcome.values[0].number == 42,
          "later queued command executes without cancelled side effect");
  require(c.cancel(epoch, later.request) == Cancellation::AlreadyTerminal,
          "completed cancellation explicit");
  require(c.cancel(epoch, 9999999) == Cancellation::Unavailable,
          "unknown cancellation explicit");
  auto stale = c.submit(epoch, "stale_side_effect=99");
  c.reset();
  auto fresh = c.status().session;
  require(fresh != epoch && c.status().queued == 0 &&
              c.complete("shared").empty(),
          "reset invalidates queues and names");
  require(c.outcome(epoch, stale.request).status == Lookup::StaleSession &&
              c.cancel(epoch, stale.request) == Cancellation::StaleSession,
          "stale session rejected");
  require(c.submit(epoch, "1").rejection == Reject::StaleSession &&
              c.snapshot(epoch, 0).status == Lookup::StaleSession,
          "stale submit and output rejected");
  auto clean = evaluate(c, "stale_side_effect");
  require(clean.request > stale.request &&
              clean.values[0].type == ValueType::Nil,
          "reset preserves monotonic IDs and drops old work");
  require(c.outcome(fresh, stale.request).status == Lookup::Unavailable,
          "old ID unavailable in new session");
  require(c.snapshot(fresh, 0).lines.front().session == fresh,
          "fresh lines carry epoch");

  Console active;
  active.pump([](lua_State *L) {
    lua_pushcfunction(L, gate);
    lua_setglobal(L, "gate");
  });
  auto active_epoch = active.status().session;
  auto running_request =
      active.submit(active_epoch, "gate(); while true do end");
  std::thread client([&] {
    {
      std::unique_lock lock(gate_mutex);
      require(gate_condition.wait_for(lock, std::chrono::seconds(3),
                                      [] { return gate_entered; }),
              "owner reached Lua gate");
    }
    require(
        active.outcome(active_epoch, running_request.request).outcome.state ==
            RequestState::Running,
        "running outcome visible coherently");
    for (int i = 0; i < 16; ++i)
      require(active.submit(active_epoch, "1").request != 0,
              "other client fills queue while running");
    require(active.submit(active_epoch, "overflow").rejection ==
                Reject::QueueFull,
            "rejection explicit while another executes");
    require(active.snapshot().back().request == 0,
            "rejection never attributed to active request");
    require(active.cancel(active_epoch, running_request.request) ==
                Cancellation::Requested,
            "running cancel only requested");
    {
      std::lock_guard lock(gate_mutex);
      gate_released = true;
    }
    gate_condition.notify_all();
  });
  active.pump();
  client.join();
  auto stopped = active.outcome(active_epoch, running_request.request).outcome;
  require(stopped.state == RequestState::Cancelled &&
              stopped.error.code == "cancelled",
          "cooperative running cancellation confirmed");
  active.pump();
  require(
      active.outcome(active_epoch, running_request.request + 1).outcome.state ==
          RequestState::Succeeded,
      "cancel does not spill to following command");
}
int main() {
  typed_tests();
  Console c;
  c.pump();
  require(!c.complete("math.sq").empty(), "initial completion");
  run(c, "nil, false, 42, 'hello'");
  require(contains(c, "result", "nil: nil"), "nil result");
  require(contains(c, "result", "boolean: false"), "false result");
  require(contains(c, "result", "number: 42"), "number result");
  run(c, "persistent = 37");
  run(c, "persistent + 5");
  require(contains(c, "result", "number: 42"), "persistent state");
  run(c, "print('standard',false,nil); io.write('write'); "
         "io.stdout:write('out'); io.stderr:write('err')");
  require(contains(c, "stdout", "standard\tfalse\tnil"), "print semantics");
  require(contains(c, "stdout", "write"), "io.write");
  require(contains(c, "stderr", "err"), "stderr handle");
  run(c, "io.type(io.stdout), io.type(io.stderr)");
  require(contains(c, "result", "string: file"),
          "standard handles retain file type");
  run(c, "local f=io.tmpfile(); io.output(f); io.write('file-write'); "
         "io.output(io.stdout); f:seek('set'); local s=f:read('*a'); "
         "f:close(); return s");
  require(contains(c, "result", "string: file-write"),
          "io.output file target preserved");
  run(c, "local function broken() error('broken') end; broken()", true);
  require(contains(c, "error", "stack traceback:"), "traceback");
  run(c, "this is invalid Lua !", true);
  require(contains(c, "error", "devtools"), "parse recovery");
  run(c, "while true do end", true);
  require(contains(c, "error", "budget exhausted"), "infinite loop budget");
  run(c, "6*7");
  require(contains(c, "result", "number: 42"), "after budget recovery");
  run(c, "evil=setmetatable({}, {__index=function() error('getter ran') end}); "
         "safe={item=1}");
  require(c.complete("evil.").empty(), "completion does not invoke getter");
  require(!c.complete("safe.i").empty(), "table completion");
  run(c, "io.write=nil");
  run(c, "20+22");
  require(contains(c, "result", "number: 42"),
          "missing io.write setup recovery");
  run(c, "print=nil; io=nil; debug=nil");
  run(c, "40+2");
  require(contains(c, "result", "number: 42"), "mutated globals do not panic");
  kp::devtools::History history;
  require(!history.navigate(true, "draft"), "empty history preserves edit");
  history.submitted("first", true);
  history.submitted("second", true);
  const std::string draft = "local function unfinished()\n  return 42\nend";
  require(history.navigate(true, draft) == "second", "history enters newest");
  require(history.navigate(true, "second") == "first", "history moves older");
  require(history.navigate(false, "first") == "second", "history moves newer");
  require(history.navigate(false, "second") == draft,
          "history restores multiline draft");
  require(!history.navigate(false, draft),
          "past draft leaves editor unchanged");
  require(history.navigate(true, draft) == "second", "history reenters");
  Console queue;
  for (int i = 0; i < 16; ++i)
    require(queue.submit("1") != 0, "queue capacity");
  require(queue.submit("overflow") == 0, "queue rejects overflow");
  require(queue.submit(std::string(16385, 'x')) == 0, "command cap");
  history.submitted("rejected", queue.submit("rejected") != 0);
  require(history.navigate(false, "second") == draft,
          "rejection retains original draft");
  history.submitted("accepted", true);
  require(history.navigate(true, "") == "accepted",
          "successful submission enters history");
  require(history.navigate(false, "accepted") == "",
          "successful submission clears old draft");
  for (int i = 0; i < 600; ++i)
    queue.output("test", std::string(1000, 'x'));
  require(queue.snapshot().size() <= 262, "output byte bound");
  std::puts("console: real LuaJIT expression, persistence, streams, "
            "tracebacks, budget, completion, queue/output bounds passed");
}
