// Review probe: drives the REAL kp::harness::drain()/execute_line() from
// src/harness/commands.cpp over a real loopback socket. Stubs in stubs.cpp.
#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

#include "harness/commands.hpp"
#include "harness/json.hpp"
#include "stubs.hpp"

using namespace std::chrono_literals;
using kp::harness::Json;

static int g_fail = 0;
static void check(bool ok, const char* what) {
    std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what);
    if (!ok) ++g_fail;
}

static unsigned short g_port = 0;

static int dial() {
    int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in sa{};
    sa.sin_family = AF_INET;
    sa.sin_port = htons(g_port);
    sa.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (::connect(fd, reinterpret_cast<sockaddr*>(&sa), sizeof sa) != 0) {
        std::perror("connect");
        std::exit(2);
    }
    return fd;
}

static void send_all(int fd, const std::string& s) {
    std::size_t off = 0;
    while (off < s.size()) {
        ssize_t n = ::send(fd, s.data() + off, s.size() - off, MSG_NOSIGNAL);
        if (n <= 0) return;   // peer may have closed; that is data for the caller
        off += static_cast<std::size_t>(n);
    }
}

struct ReadResult {
    std::vector<std::string> lines;
    bool eof = false;
    bool reset = false;
};

// Read until EOF/RST or `quiet` passes with no data (bounded by `total`).
static ReadResult read_lines(int fd, std::chrono::milliseconds quiet, std::chrono::milliseconds total) {
    ReadResult r;
    std::string buf;
    auto deadline = std::chrono::steady_clock::now() + total;
    while (std::chrono::steady_clock::now() < deadline) {
        pollfd p{fd, POLLIN, 0};
        int n = ::poll(&p, 1, static_cast<int>(quiet.count()));
        if (n == 0) break;
        char tmp[8192];
        ssize_t got = ::recv(fd, tmp, sizeof tmp, 0);
        if (got == 0) { r.eof = true; break; }
        if (got < 0) { if (errno == ECONNRESET) r.reset = true; r.eof = true; break; }
        buf.append(tmp, static_cast<std::size_t>(got));
    }
    std::size_t s = 0, nl;
    while ((nl = buf.find('\n', s)) != std::string::npos) { r.lines.push_back(buf.substr(s, nl - s)); s = nl + 1; }
    if (s < buf.size()) r.lines.push_back(buf.substr(s) + "<no-newline>");
    return r;
}

static int submits() { return probe::submit_plain.load() + probe::submit_session.load(); }

static bool wait_for(const std::function<bool()>& f, std::chrono::milliseconds t) {
    auto d = std::chrono::steady_clock::now() + t;
    while (std::chrono::steady_clock::now() < d) { if (f()) return true; std::this_thread::sleep_for(1ms); }
    return f();
}

// Let the listener queue what was sent. The listener reads in 4 KiB recv()s
// with a 5 ms select; everything here is small unless stated.
static void settle(std::chrono::milliseconds t = 40ms) { std::this_thread::sleep_for(t); }

static void drain_until_idle(int rounds = 6) {
    for (int i = 0; i < rounds; ++i) { kp::harness::drain(); settle(10ms); }
}


// Drain on this thread and read until EOF or `total` passes; bytes are
// accumulated across reads so a split reply is not misread.
static ReadResult pump_read(int fd, std::chrono::milliseconds total, bool stop_on_line = false) {
    ReadResult r;
    std::string buf;
    auto deadline = std::chrono::steady_clock::now() + total;
    while (std::chrono::steady_clock::now() < deadline) {
        kp::harness::drain();
        pollfd p{fd, POLLIN, 0};
        if (::poll(&p, 1, 5) > 0) {
            char tmp[8192];
            ssize_t got = ::recv(fd, tmp, sizeof tmp, 0);
            if (got == 0) { r.eof = true; break; }
            if (got < 0) { if (errno == ECONNRESET) r.reset = true; r.eof = true; break; }
            buf.append(tmp, static_cast<std::size_t>(got));
            if (stop_on_line && buf.find('\n') != std::string::npos) break;
        }
    }
    std::size_t s = 0, nl;
    while ((nl = buf.find('\n', s)) != std::string::npos) { r.lines.push_back(buf.substr(s, nl - s)); s = nl + 1; }
    if (s < buf.size()) r.lines.push_back(buf.substr(s) + "<no-newline>");
    return r;
}

static int dial_ready() {
    const int c0 = probe::connected.load();
    int fd = dial();
    wait_for([&] { return probe::connected.load() > c0; }, 3000ms);
    return fd;
}

static void close_well_formed(int fd) {
    const int d0 = probe::disconnected.load();
    ::close(fd);
    wait_for([&] { return probe::disconnected.load() > d0; }, 3000ms);
}

static std::string g_runtime;
static const std::string kPlainBody = R"J({"cmd":"devtools","op":"submit","code":"os.execute('id')"})J";
static std::string proto_body() {
    return R"J({"cmd":"devtools","protocol":"kp.console.v1","op":"submit","runtime":")J" + g_runtime +
           R"J(","session":"1","code":"os.execute('id')"})J";
}

static bool reply_ok(const std::string& line) {
    Json j; std::string e;
    if (!Json::parse(line, j, e)) return false;
    const Json* ok = j.get("ok");
    return ok && ok->as_bool();
}
static std::string reply_error(const std::string& line) {
    Json j; std::string e;
    if (!Json::parse(line, j, e)) return "<unparsable>";
    const Json* er = j.get("error");
    return er ? er->as_string() : "";
}

// A condemned-shape case: send `payload` in one send, drain until idle, expect
// exactly one error reply then EOF, and zero submits.
static void condemned_case(const char* name, const std::string& payload, const char* want_substr = nullptr) {
    std::printf("-- %s\n", name);
    const int before = submits();
    int fd = dial_ready();
    send_all(fd, payload);
    ReadResult r = pump_read(fd, 3000ms);
    for (auto& l : r.lines) std::printf("    got: %s\n", l.c_str());
    std::printf("    eof=%d reset=%d submits+%d\n", r.eof, r.reset, submits() - before);
    check(r.lines.size() == 1 && !reply_ok(r.lines[0]), "exactly one error reply");
    if (want_substr && !r.lines.empty())
        check(reply_error(r.lines[0]).find(want_substr) != std::string::npos, "reply wording");
    check(r.eof, "connection closed");
    check(submits() == before, "nothing after the bad line ran");
    ::close(fd);
    settle(20ms);
}

static std::string post(int headers, const std::string& body) {
    std::string s = "POST / HTTP/1.1\r\nHost: 127.0.0.1\r\n";
    for (int i = 1; i < headers; ++i) s += "X-H" + std::to_string(i) + ": v\r\n";
    s += "Content-Type: text/plain\r\n\r\n" + body + "\n";
    return s;
}

int main(int argc, char** argv) {
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    if (argc > 1 && std::string(argv[1]) == "-v") probe::verbose = true;
    std::string err;
    kp::harness::HarnessOptions opts;
    if (!kp::harness::start(opts, err)) { std::printf("start failed: %s\n", err.c_str()); return 2; }
    g_port = kp::harness::listening_port();
    std::printf("real commands.cpp drain on 127.0.0.1:%u\n", g_port);

    // ---- well-formed client: learn the console runtime identity (worst case
    // for the attacker: assume it is known), and prove the baseline works.
    {
        std::printf("-- baseline: well-formed client\n");
        int fd = dial_ready();
        send_all(fd, R"J({"id":1,"cmd":"devtools","protocol":"kp.console.v1","op":"status"})J" "\n");
        settle();
        drain_until_idle(2);
        ReadResult r = read_lines(fd, 100ms, 1000ms);
        check(r.lines.size() == 1 && reply_ok(r.lines[0]) && !r.eof, "status answered, connection kept");
        Json j; std::string e;
        if (!r.lines.empty() && Json::parse(r.lines[0], j, e) && j.get("result"))
            if (const Json* rt = j.get("result")->get("runtime")) g_runtime = rt->as_string();
        std::printf("    runtime=%s\n", g_runtime.c_str());
        ::close(fd);
        wait_for([] { return probe::disconnected.load() >= 1; }, 1000ms);
        settle(20ms);
    }

    // ---- (a) spec shape, both body kinds, one send
    condemned_case("(a) POST + plain submit body, one send", post(1, kPlainBody), "HTTP");
    condemned_case("(a) POST + kp.console.v1 submit body, one send", post(1, proto_body()), "HTTP");

    // ---- (a2) cross-batch, deterministic: body is exactly line 9, i.e. the
    // first line of batch 2. The listener is parked after the error send and
    // before close_client(), so the connection is still current and the body
    // is still queued when drain #2 takes it. Only admit() can refuse it.
    for (int kind = 0; kind < 2; ++kind) {
        std::printf("-- (a2) parked cross-batch, body first in batch 2 (%s)\n", kind ? "protocol" : "plain");
        const int before = submits();
        const int connected0 = probe::connected.load();
        int fd = dial();
        wait_for([&] { return probe::connected.load() > connected0; }, 1000ms);
        // request line + Host + X-H1..X-H5 + Content-Type = 8 lines, blank skipped, body = 9th.
        std::string p = post(6, kind ? proto_body() : kPlainBody);
        send_all(fd, p);
        settle();
        probe::arm_park();
        kp::harness::drain();                       // batch 1: request line condemns, 7 skipped
        const bool parked = wait_for([] { return probe::parked.load(); }, 1000ms);
        check(parked, "listener parked on condemnation (condemn() reached the listener)");
        kp::harness::drain();                       // batch 2: the body, connection still current
        const int ran = submits() - before;
        probe::release_park();
        ReadResult r = read_lines(fd, 150ms, 2000ms);
        for (auto& l : r.lines) std::printf("    got: %s\n", l.c_str());
        std::printf("    batch-2 body executed: %d; eof=%d\n", ran, r.eof);
        check(ran == 0, "body in batch 2 of a condemned client is not executed");
        check(r.lines.size() == 1, "only the one error reply is delivered");
        check(r.eof, "connection closed");
        ::close(fd);
        settle(30ms);
        probe::park_enabled.store(false);
    }

    // ---- (b) malformed then valid, same batch
    condemned_case("(b) {bad json + valid submit", "{bad json\n" + kPlainBody + "\n");
    condemned_case("(b') {\"cmd\": truncated object + valid", "{\"cmd\":\n" + kPlainBody + "\n");

    // ---- non-object JSON and oddities, each followed by a valid submit
    condemned_case("non-object: array", "[1,2]\n" + kPlainBody + "\n", "JSON object");
    condemned_case("non-object: number", "123\n" + kPlainBody + "\n", "JSON object");
    condemned_case("non-object: string", "\"string\"\n" + kPlainBody + "\n", "JSON object");
    condemned_case("non-object: true", "true\n" + kPlainBody + "\n", "JSON object");
    condemned_case("non-object: null", "null\n" + kPlainBody + "\n", "JSON object");
    condemned_case("whitespace-only line", "   \t \n" + kPlainBody + "\n", "JSON object");
    condemned_case("BOM before object", "\xEF\xBB\xBF" + kPlainBody + "\n" + kPlainBody + "\n", "JSON object");
    condemned_case("object + trailing garbage", R"J({"cmd":"devtools","op":"status"} xyz)J" "\n" + kPlainBody + "\n");
    std::string deep; for (int i = 0; i < 100; ++i) deep += "{\"a\":"; deep += "1"; deep += std::string(100, '}');
    condemned_case("deep nesting 100 objects", deep + "\n" + kPlainBody + "\n", "nested");
    condemned_case("WebSocket upgrade",
                   "GET /chat HTTP/1.1\r\nHost: 127.0.0.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                   "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\nSec-WebSocket-Version: 13\r\n\r\n" +
                       kPlainBody + "\n",
                   "HTTP");
    condemned_case("HTTP/2 preface", std::string("PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n") + kPlainBody + "\n", "HTTP");
    condemned_case("TLS-ish binary with embedded JSON line",
                   std::string("\x16\x03\x01\x02\x00\x01\x00\x01\xfc\x03\x03", 11) + "\n" + kPlainBody + "\n");
    condemned_case("pipelined: two POSTs in one send", post(2, kPlainBody) + post(2, proto_body()), "HTTP");
    condemned_case("OPTIONS preflight then body", "OPTIONS / HTTP/1.1\r\nHost: x\r\n\r\n" + kPlainBody + "\n", "HTTP");
    condemned_case("lowercase method (not in list)", "post / HTTP/1.1\r\n" + kPlainBody + "\n", "HTTP");

    // ---- (c) stale generation inside one batch, deterministic via the
    // submit hook: on the first submit, A disconnects and B connects; the rest
    // of A's batch must not run.
    {
        std::printf("-- (c) client leaves mid-batch, new client connects\n");
        const int before = submits();
        int a = dial_ready();
        settle(15ms);
        send_all(a, kPlainBody + "\n" + kPlainBody + "\n" + kPlainBody + "\n");
        settle();
        int b = -1;
        bool swapped = false;
        bool fired = false;
        probe::on_submit = [&] {
            if (fired) return;
            fired = true;
            const int d0 = probe::disconnected.load(), c0 = probe::connected.load();
            ::close(a);
            wait_for([&] { return probe::disconnected.load() > d0; }, 1000ms);
            b = dial();
            swapped = wait_for([&] { return probe::connected.load() > c0; }, 1000ms);
        };
        for (int i = 0; i < 600 && !fired; ++i) { kp::harness::drain(); settle(5ms); }
        kp::harness::drain();
        probe::on_submit = nullptr;
        check(swapped, "A left and B connected during A's batch");
        std::printf("    A's batch executed: %d of 3\n", submits() - before);
        check(submits() - before == 1, "only the request that was running when A left ran");
        // B is fresh and works.
        send_all(b, R"J({"id":7,"cmd":"devtools","op":"status"})J" "\n");
        settle();
        drain_until_idle(2);
        ReadResult r = read_lines(b, 100ms, 1000ms);
        check(r.lines.size() == 1 && reply_ok(r.lines[0]) && !r.eof, "B answered and kept (A's replies not delivered to B)");
        for (auto& l : r.lines) std::printf("    B got: %s\n", l.c_str());
        close_well_formed(b);
    }

    // ---- fresh generation after condemnation is not poisoned
    {
        std::printf("-- fresh client after a condemned one\n");
        int c = dial_ready();
        send_all(c, "GET / HTTP/1.1\r\n\r\n");
        settle();
        drain_until_idle(2);
        ReadResult r1 = read_lines(c, 100ms, 1000ms);
        check(r1.eof, "condemned client closed");
        ::close(c);
        const int before = submits();
        int d = dial_ready();
        send_all(d, R"J({"id":1,"cmd":"devtools","op":"status"})J" "\n" + kPlainBody + "\n" +
                        R"J({"id":3,"note":"no cmd"})J" "\n" + kPlainBody + "\n");
        settle();
        drain_until_idle(2);
        ReadResult r = read_lines(d, 150ms, 1000ms);
        for (auto& l : r.lines) std::printf("    got: %s\n", l.c_str());
        check(r.lines.size() == 4 && !r.eof, "four replies, connection kept");
        check(submits() - before == 2, "both submits ran on the fresh generation");
        check(r.lines.size() == 4 && !reply_ok(r.lines[2]) && reply_ok(r.lines[3]),
              "object without cmd is answered and does not condemn");
        close_well_formed(d);
    }

    // ---- valid formatting variants on one connection
    {
        std::printf("-- valid variants: leading ws, tab, CRLF, HTTP text in code\n");
        const int before = submits();
        int d = dial_ready();
        send_all(d, "   " + kPlainBody + "\r\n\t" + kPlainBody + "\n" +
                        R"J({"cmd":"devtools","op":"submit","code":"-- POST / HTTP/1.1"})J" "\r\n");
        settle();
        drain_until_idle(2);
        ReadResult r = read_lines(d, 150ms, 1000ms);
        check(r.lines.size() == 3 && !r.eof && submits() - before == 3, "3 answered, 3 ran, kept");
        close_well_formed(d);
    }

    // ---- busy during the park window, then fresh after
    {
        std::printf("-- second connection while a condemned client is still open\n");
        int c = dial_ready();
        send_all(c, "GET / HTTP/1.1\r\n");
        settle();
        probe::arm_park();
        for (int i = 0; i < 600 && !probe::parked.load(); ++i) { kp::harness::drain(); settle(5ms); }
        // Listener is parked, so it cannot accept now; connect completes in the
        // backlog and is served after release, when the condemned one is gone.
        int e = dial();
        probe::release_park();
        settle(40ms);
        ReadResult rc = read_lines(c, 100ms, 1000ms);
        send_all(e, R"J({"id":9,"cmd":"devtools","op":"status"})J" "\n");
        settle();
        drain_until_idle(2);
        ReadResult re = read_lines(e, 100ms, 1000ms);
        for (auto& l : re.lines) std::printf("    e got: %s (eof=%d)\n", l.c_str(), re.eof);
        check(rc.eof, "condemned closed");
        check(re.lines.size() == 1 && reply_ok(re.lines[0]) && !re.eof,
              "backlogged connection accepted after the close is a fresh generation");
        ::close(c);
        close_well_formed(e);
        probe::park_enabled.store(false);
    }

    // ---- long lines
    {
        std::printf("-- long valid line (900 KiB code)\n");
        const int before = submits();
        int d = dial_ready();
        std::string big = R"J({"cmd":"devtools","op":"submit","code":")J" + std::string(900 * 1024, 'a') + "\"}\n";
        std::thread t([&] { send_all(d, big); });
        ReadResult r = pump_read(d, 10000ms, true);
        t.join();
        for (auto& l : r.lines) std::printf("    got: %s\n", l.substr(0, 160).c_str());
        check(r.lines.size() == 1 && reply_ok(r.lines[0]) && submits() - before == 1, "answered and ran");
        close_well_formed(d);
    }
    {
        std::printf("-- over-long line (1.2 MiB, no newline) then a valid line\n");
        const int before = submits();
        int d = dial_ready();
        std::string big = "{" + std::string(1200 * 1024, 'a') + "\n" + kPlainBody + "\n";
        std::thread t([&] { send_all(d, big); });
        ReadResult r;
        for (int i = 0; i < 300 && !r.eof; ++i) {
            kp::harness::drain();
            ReadResult x = read_lines(d, 10ms, 20ms);
            r.lines.insert(r.lines.end(), x.lines.begin(), x.lines.end());
            r.eof = x.eof; r.reset = x.reset;
        }
        t.join();
        for (auto& l : r.lines) std::printf("    got: %s\n", l.substr(0, 120).c_str());
        std::printf("    eof=%d reset=%d\n", r.eof, r.reset);
        check(r.eof && submits() == before, "closed, nothing ran");
        close_well_formed(d);
    }

    // ---- RST probe: the condemned client keeps sending after the bad line,
    // so the listener closes with unread bytes. Does the error line survive?
    {
        std::printf("-- RST probe: 256 KiB of junk after the request line\n");
        const int before = submits();
        int d = dial_ready();
        std::string junk = "POST / HTTP/1.1\r\n";
        while (junk.size() < 256 * 1024) junk += "X-Pad: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\r\n";
        junk += "\r\n" + kPlainBody + "\n";
        std::thread t([&] { send_all(d, junk); });
        settle(20ms);
        ReadResult r;
        for (int i = 0; i < 100 && !r.eof; ++i) {
            kp::harness::drain();
            ReadResult x = read_lines(d, 10ms, 20ms);
            r.lines.insert(r.lines.end(), x.lines.begin(), x.lines.end());
            r.eof = x.eof; r.reset = x.reset;
        }
        t.join();
        std::printf("    lines=%zu eof=%d reset=%d submits+%d\n", r.lines.size(), r.eof, r.reset, submits() - before);
        check(r.eof && submits() == before, "closed, nothing ran");
        std::printf("    (informational) error line delivered: %s\n", r.lines.empty() ? "no" : "yes");
        close_well_formed(d);
    }

    kp::harness::stop();
    std::printf("%d failure(s)\n", g_fail);
    return g_fail == 0 ? 0 : 1;
}
