#include "harness/console_protocol.hpp"
#include <cstdio>
#include <cstdlib>
#include <limits>
using namespace kp::harness;
using kp::devtools::Console;
namespace wire = kp::harness::console_protocol;
void check(bool v, const char *message) {
  if (!v) {
    std::fprintf(stderr, "FAIL %s\n", message);
    std::exit(1);
  }
}
const Json &at(const Json &j, const char *k) {
  const auto *v = j.get(k);
  check(v != nullptr, k);
  return *v;
}
std::string text(const Json &j, const char *k) { return at(j, k).as_string(); }
Json req(Console &c, const char *op) {
  Json j = Json::object();
  j.set("protocol", Json::string("kp.console.v1"));
  j.set("op", Json::string(op));
  j.set("runtime", Json::string("runtime-A"));
  j.set("session", wire::decimal(c.status().session));
  return j;
}
Json run(Console &c, const Json &q) {
  Json r;
  std::string e;
  const bool ok =
      wire::dispatch(c, q, "runtime-A", true, 9007199254740993ull, r, e);
  if (!ok)
    std::fprintf(stderr, "request %s error %s\n", q.dump().c_str(), e.c_str());
  check(ok, "dispatch accepted");
  Json parsed;
  check(Json::parse(r.dump(), parsed, e), "response valid JSON");
  return parsed;
}
Json submit(Console &c, const std::string &code) {
  auto q = req(c, "submit");
  q.set("code", Json::string(code));
  auto r = run(c, q);
  check(text(r, "status") == "None", "accepted");
  return r;
}
Json outcome(Console &c, const Json &receipt) {
  auto q = req(c, "outcome");
  q.set("session", at(receipt, "session"));
  q.set("request", at(receipt, "request"));
  return run(c, q);
}
int main() {
  Console c;
  auto s = run(c, req(c, "status"));
  check(text(s, "input_calls") == "9007199254740993",
        "counter above2^53 lossless");
  check(wire::decimal(std::numeric_limits<std::uint64_t>::max()).as_string() ==
            "18446744073709551615",
        "uint64 max lossless");
  check(wire::runtime_instance().size() == 64 &&
            wire::runtime_instance() == wire::runtime_instance(),
        "runtime identity stable");
  Json r;
  std::string e;
  check(!wire::dispatch(c, req(c, "status"), "", false, 0, r, e),
        "no weak runtime fallback");
  auto q = req(c, "submit");
  q.set("runtime", Json::string("old-runtime"));
  q.set("code", Json::string("error('must not run')"));
  check(text(run(c, q), "status") == "StaleRuntime" &&
            c.status().submitted == 0,
        "stale runtime cannot mutate");
  for (const char *invalid :
       {"", "0", "01", "-1", "+1", " 1", "1.0", "18446744073709551616"}) {
    q = req(c, "cancel");
    q.set("request", Json::string(invalid));
    check(!wire::dispatch(c, q, "runtime-A", false, 0, r, e),
          "invalid id rejected");
  }
  q = req(c, "cancel");
  q.set("request", Json::number(1));
  check(!wire::dispatch(c, q, "runtime-A", false, 0, r, e),
        "numeric id rejected");
  q = req(c, "cancel");
  q.set("request", wire::decimal(9007199254740993ull));
  check(text(run(c, q), "status") == "Unavailable",
        "large exact id not rounded");
  q = req(c, "status");
  q.set("protocol", Json::string("kp.console.v2"));
  check(!wire::dispatch(c, q, "runtime-A", false, 0, r, e),
        "unknown protocol refuses");
  q = req(c, "output");
  q.set("after_sequence", Json::number(0));
  check(!wire::dispatch(c, q, "runtime-A", false, 0, r, e),
        "numeric cursor refuses");
  q = req(c, "submit");
  q.set("session", Json::number(1));
  q.set("code", Json::string("return 1"));
  check(!wire::dispatch(c, q, "runtime-A", false, 0, r, e) &&
            c.status().submitted == 0,
        "malformed session does not submit");
  auto receipt = submit(c, "return nil, false, 42, string.char(0,255,65), {}, "
                           "-1/math.huge, 0/0, 1/0, -1/0");
  check(text(at(outcome(c, receipt), "outcome"), "state") == "Pending",
        "pending retained");
  c.pump();
  auto done = at(outcome(c, receipt), "outcome");
  check(text(done, "state") == "Succeeded" && text(done, "return_count") == "9",
        "actual Lua tuple");
  const auto &values = at(done, "values").elements();
  check(text(values[0], "type") == "Nil" && !at(values[1], "value").as_bool(),
        "nil false preserved");
  check(text(at(values[3], "bytes"), "data") == "AP9B" &&
            text(values[3], "original_bytes") == "3",
        "binary string lossless");
  check(!at(values[4], "inspection_available").as_bool() &&
            !values[4].has("address"),
        "opaque noninspectable");
  check(text(values[5], "kind") == "NegativeZero" &&
            text(values[6], "kind") == "NaN" &&
            text(values[7], "kind") == "PositiveInfinity" &&
            text(values[8], "kind") == "NegativeInfinity",
        "special numbers explicit");
  for (const char *source : {"return", "return nil"}) {
    auto x = submit(c, source);
    c.pump();
    auto o = at(outcome(c, x), "outcome");
    check(text(o, "return_count") ==
              (std::string(source) == "return" ? "0" : "1"),
          "empty versus nil tuple");
  }
  for (const char *source :
       {"local =", "error(string.char(0,255))", "while true do end"}) {
    auto x = submit(c, source);
    c.pump();
    auto o = at(outcome(c, x), "outcome");
    check(text(o, "state") == "Failed" && !text(at(o, "error"), "code").empty(),
          "structured error distinct from watermark");
    check(text(at(at(o, "error"), "text"), "encoding") == "base64",
          "error bytes encoded");
  }
  auto cancelled = submit(c, "error('cancelled body executed')");
  auto next = submit(c, "return 9");
  q = req(c, "cancel");
  q.set("request", at(cancelled, "request"));
  check(text(run(c, q), "status") == "Cancelled", "exact queued cancellation");
  c.pump();
  check(text(at(outcome(c, cancelled), "outcome"), "state") == "Cancelled" &&
            text(at(outcome(c, next), "outcome"), "state") == "Succeeded",
        "cancel does not spill");
  check(text(run(c, q), "status") == "AlreadyTerminal",
        "terminal cancel explicit");
  auto old = req(c, "output");
  old.set("after_sequence", wire::decimal(0));
  c.reset();
  check(text(run(c, old), "status") == "StaleSession",
        "reset invalidates epoch");
  q = req(c, "submit");
  q.set("session", at(old, "session"));
  q.set("code", Json::string("return 1"));
  check(text(run(c, q), "status") == "StaleSession", "stale submit refuses");
  auto first = submit(c, "return 1");
  c.pump();
  for (int i = 0; i < 140; ++i) {
    submit(c, "return 2");
    c.pump();
  }
  check(text(outcome(c, first), "status") == "Expired",
        "terminal eviction explicit");
  c.output("stdout", std::string("\0\xff", 2));
  q = req(c, "output");
  q.set("after_sequence", wire::decimal(0));
  auto output = run(c, q);
  check(text(at(output, "lines").elements().back(), "request") == "0",
        "unattributed output preserved");
  check(text(at(at(output, "lines").elements().back(), "text"), "data") ==
            "AP8=",
        "raw output encoded");
  for (int i = 0; i < 600; ++i)
    c.output("stderr", std::string(8192, 'x'));
  output = run(c, q);
  check(text(output, "dropped_lines") != "0" &&
            text(output, "dropped_through") != "0",
        "output eviction metadata");
  check(output.dump().size() < 1024 * 1024,
        "bounded base64 output fits channel line");
  auto large = submit(c, "return string.rep('x',9000)");
  c.pump();
  auto lo = at(outcome(c, large), "outcome");
  check(at(lo, "returns_truncated").as_bool() &&
            text(at(lo, "values").elements()[0], "original_bytes") == "9000",
        "truncation explicit");
  q = req(c, "complete");
  q.set("prefix", Json::string("str"));
  check(text(run(c, q), "status") == "Found", "completion shared service");
  q = req(c, "submit");
  q.set("code", Json::string(std::string(16385, 'x')));
  check(text(run(c, q), "status") == "SourceLimit", "source limit explicit");
  for (int i = 0; i < 16; ++i)
    submit(c, "return 1");
  q.set("code", Json::string("return 1"));
  check(text(run(c, q), "status") == "QueueFull", "queue limit explicit");
  q = req(c, "reset");
  check(!wire::dispatch(c, q, "runtime-A", false, 0, r, e),
        "reset not exported");
  std::puts("PASS console protocol actual Lua/serialization/lifecycle/bounds");
}
