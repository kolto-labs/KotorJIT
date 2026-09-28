#include "harness/console_protocol.hpp"
#include <cmath>
#include <limits>
#include <random>
#include <stdexcept>

namespace kp::harness::console_protocol {
namespace {
using namespace devtools;
const char *lookup(Lookup v) {
  switch (v) {
  case Lookup::Found:
    return "Found";
  case Lookup::StaleSession:
    return "StaleSession";
  case Lookup::Expired:
    return "Expired";
  case Lookup::Unavailable:
    return "Unavailable";
  }
  return "Unavailable";
}
const char *state(RequestState v) {
  switch (v) {
  case RequestState::Pending:
    return "Pending";
  case RequestState::Running:
    return "Running";
  case RequestState::Succeeded:
    return "Succeeded";
  case RequestState::Failed:
    return "Failed";
  case RequestState::Cancelled:
    return "Cancelled";
  }
  return "Failed";
}
const char *rejected(Reject v) {
  switch (v) {
  case Reject::None:
    return "None";
  case Reject::StaleSession:
    return "StaleSession";
  case Reject::QueueFull:
    return "QueueFull";
  case Reject::SourceLimit:
    return "SourceLimit";
  }
  return "SourceLimit";
}
const char *cancellation(Cancellation v) {
  switch (v) {
  case Cancellation::Cancelled:
    return "Cancelled";
  case Cancellation::Requested:
    return "Requested";
  case Cancellation::AlreadyTerminal:
    return "AlreadyTerminal";
  case Cancellation::StaleSession:
    return "StaleSession";
  case Cancellation::Expired:
    return "Expired";
  case Cancellation::Unavailable:
    return "Unavailable";
  }
  return "Unavailable";
}
bool id(const Json &req, const char *key, std::uint64_t &out,
        bool zero = false) {
  const auto *j = req.get(key);
  if (!j || !j->is_string())
    return false;
  const auto &s = j->as_string();
  if (s.empty() || s.size() > 20 || (s.size() > 1 && s[0] == '0'))
    return false;
  out = 0;
  for (char c : s) {
    if (c < '0' || c > '9' ||
        out > (std::numeric_limits<std::uint64_t>::max() - (c - '0')) / 10)
      return false;
    out = out * 10 + (c - '0');
  }
  return zero || out != 0;
}
Json value(const ReturnValue &v) {
  Json j = Json::object();
  switch (v.type) {
  case ValueType::Nil:
    j.set("type", Json::string("Nil"));
    break;
  case ValueType::Boolean:
    j.set("type", Json::string("Boolean"));
    j.set("value", Json::boolean(v.boolean));
    break;
  case ValueType::Number: {
    j.set("type", Json::string("Number"));
    const char *kind = "Finite";
    if (v.number_kind == NumberKind::NaN)
      kind = "NaN";
    else if (v.number_kind == NumberKind::PositiveInfinity)
      kind = "PositiveInfinity";
    else if (v.number_kind == NumberKind::NegativeInfinity)
      kind = "NegativeInfinity";
    else if (v.number == 0 && std::signbit(v.number))
      kind = "NegativeZero";
    j.set("kind", Json::string(kind));
    if (std::string(kind) == "Finite")
      j.set("value", Json::number(v.number));
    break;
  }
  case ValueType::String:
    j.set("type", Json::string("String"));
    j.set("bytes", bytes(v.bytes));
    j.set("original_bytes", decimal(v.original_bytes));
    j.set("truncated", Json::boolean(v.truncated));
    break;
  case ValueType::Opaque:
    j.set("type", Json::string("Opaque"));
    j.set("lua_type", bytes(v.opaque_type));
    j.set("inspection_available", Json::boolean(false));
    break;
  }
  return j;
}
} // namespace
Json decimal(std::uint64_t v) { return Json::string(std::to_string(v)); }
Json bytes(const std::string &s) {
  static constexpr char alphabet[] =
      "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  std::string encoded;
  encoded.reserve((s.size() + 2) / 3 * 4);
  for (std::size_t i = 0; i < s.size(); i += 3) {
    const auto a = static_cast<unsigned char>(s[i]);
    const auto b = i + 1 < s.size() ? static_cast<unsigned char>(s[i + 1]) : 0;
    const auto c = i + 2 < s.size() ? static_cast<unsigned char>(s[i + 2]) : 0;
    encoded += alphabet[a >> 2];
    encoded += alphabet[((a & 3) << 4) | (b >> 4)];
    encoded += i + 1 < s.size() ? alphabet[((b & 15) << 2) | (c >> 6)] : '=';
    encoded += i + 2 < s.size() ? alphabet[c & 63] : '=';
  }
  Json j = Json::object();
  j.set("encoding", Json::string("base64"));
  j.set("data", Json::string(std::move(encoded)));
  j.set("byte_length", decimal(s.size()));
  return j;
}
Json outcome(const devtools::Outcome &o) {
  Json j = Json::object(), values = Json::array(), error = Json::object();
  j.set("session", decimal(o.session));
  j.set("request", decimal(o.request));
  j.set("state", Json::string(state(o.state)));
  for (const auto &v : o.values)
    values.push(value(v));
  j.set("values", std::move(values));
  j.set("return_count", decimal(o.return_count));
  j.set("returns_truncated", Json::boolean(o.returns_truncated));
  error.set("code", Json::string(o.error.code));
  error.set("text", bytes(o.error.text));
  error.set("truncated", Json::boolean(o.error.truncated));
  j.set("error", std::move(error));
  j.set("first_line", decimal(o.first_line));
  j.set("last_line", decimal(o.last_line));
  return j;
}
const std::string &runtime_instance() {
  static const std::string identity = [] {
    try {
      std::random_device entropy;
      static constexpr char hex[] = "0123456789abcdef";
      std::string s;
      for (unsigned i = 0; i < 8; ++i) {
        auto word = entropy();
        for (unsigned n = 0; n < 8; ++n) {
          s += hex[word & 15];
          word >>= 4;
        }
      }
      return s;
    } catch (...) {
      return std::string{};
    } // no weak fallback or engine unwind
  }();
  return identity;
}
bool dispatch(devtools::Console &c, const Json &req, const std::string &runtime,
              bool open, std::uint64_t input_calls, Json &result,
              std::string &error) {
  error.clear();
  result = Json::object();
  auto bad = [&](const char *text) {
    error = text;
    return false;
  };
  if (runtime.empty())
    return bad("console protocol runtime identity unavailable");
  const auto *protocol = req.get("protocol");
  if (!protocol || !protocol->is_string() ||
      protocol->as_string() != "kp.console.v1")
    return bad("unsupported console protocol");
  const auto *opj = req.get("op");
  if (opj && !opj->is_string())
    return bad("op must be a string");
  const auto op = opj ? opj->as_string() : "status";
  if (op != "status" && op != "submit" && op != "outcome" && op != "output" &&
      op != "complete" && op != "cancel")
    return bad("unknown console operation");
  result.set("protocol", Json::string("kp.console.v1"));
  result.set("runtime", Json::string(runtime));
  const auto *runtimej = req.get("runtime");
  if (op != "status" && (!runtimej || !runtimej->is_string()))
    return bad("runtime string is required");
  if (runtimej && !runtimej->is_string())
    return bad("runtime must be a string");
  if (runtimej && runtimej->as_string() != runtime) {
    result.set("status", Json::string("StaleRuntime"));
    return true;
  }
  if (op == "status") {
    const auto s = c.status();
    result.set("status", Json::string("Found"));
    result.set("session", decimal(s.session));
    result.set("submitted", decimal(s.submitted));
    result.set("completed", decimal(s.completed));
    result.set("running", Json::boolean(s.running));
    result.set("queued", decimal(s.queued));
    result.set("last_line", decimal(s.last_line));
    result.set("dropped_lines", decimal(s.dropped_lines));
    result.set("open", Json::boolean(open));
    result.set("input_calls", decimal(input_calls));
    return true;
  }
  std::uint64_t session = 0, request = 0, cursor = 0;
  if (!id(req, "session", session))
    return bad("session must be a nonzero canonical uint64 decimal string");
  if ((op == "outcome" || op == "cancel") && !id(req, "request", request))
    return bad("request must be a nonzero canonical uint64 decimal string");
  if (op == "output" && !id(req, "after_sequence", cursor, true))
    return bad("after_sequence must be a canonical uint64 decimal string");
  if (op == "submit") {
    const auto *code = req.get("code");
    if (!code || !code->is_string())
      return bad("code must be a string");
    const auto r = c.submit(session, code->as_string());
    result.set("status", Json::string(rejected(r.rejection)));
    result.set("session", decimal(r.session));
    result.set("request", decimal(r.request));
  } else if (op == "outcome") {
    const auto r = c.outcome(session, request);
    result.set("status", Json::string(lookup(r.status)));
    if (r.status == Lookup::Found)
      result.set("outcome", outcome(r.outcome));
  } else if (op == "cancel") {
    result.set("status",
               Json::string(cancellation(c.cancel(session, request))));
  } else if (op == "output") {
    const auto r = c.snapshot(session, cursor);
    result.set("status", Json::string(lookup(r.status)));
    result.set("session", decimal(r.session));
    result.set("last_sequence", decimal(r.last_sequence));
    result.set("dropped_lines", decimal(r.dropped_lines));
    result.set("dropped_through", decimal(r.dropped_through));
    Json lines = Json::array();
    for (const auto &l : r.lines) {
      Json line = Json::object();
      line.set("session", decimal(l.session));
      line.set("request", decimal(l.request));
      line.set("sequence", decimal(l.sequence));
      line.set("kind", bytes(l.kind));
      line.set("text", bytes(l.text));
      lines.push(std::move(line));
    }
    result.set("lines", std::move(lines));
  } else {
    const auto *prefix = req.get("prefix");
    if (!prefix || !prefix->is_string() || prefix->as_string().size() > 16384)
      return bad("bounded prefix string is required");
    if (c.status().session != session) {
      result.set("status", Json::string("StaleSession"));
      return true;
    }
    Json names = Json::array();
    for (const auto &n : c.complete(prefix->as_string()))
      names.push(bytes(n));
    if (c.status().session != session) {
      result.set("status", Json::string("StaleSession"));
      return true;
    }
    result.set("status", Json::string("Found"));
    result.set("names", std::move(names));
  }
  return true;
}
} // namespace kp::harness::console_protocol
