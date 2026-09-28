#include "devtools/console.hpp"
#include <cstdio>
#include <cstdlib>
#include <string>
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
int main() {
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
  Console queue;
  for (int i = 0; i < 16; ++i)
    require(queue.submit("1") != 0, "queue capacity");
  require(queue.submit("overflow") == 0, "queue rejects overflow");
  require(queue.submit(std::string(16385, 'x')) == 0, "command cap");
  for (int i = 0; i < 600; ++i)
    queue.output("test", std::string(1000, 'x'));
  require(queue.snapshot().size() <= 262, "output byte bound");
  std::puts("console: real LuaJIT expression, persistence, streams, "
            "tracebacks, budget, completion, queue/output bounds passed");
}
