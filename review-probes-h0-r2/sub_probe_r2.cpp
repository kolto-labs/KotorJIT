// Re-review probe (r2): real drain()/execute_line()/stream_events() from
// commands.cpp over loopback, stubs from review-probes-h0. Independent of the
// writer's subscriber_probe.cpp.
#include <arpa/inet.h>
#include <netinet/in.h>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <functional>
#include <string>
#include <thread>
#include <vector>
#include "harness/commands.hpp"
#include "harness/ring.hpp"
#include "stubs.hpp"
using namespace std::chrono_literals;
static int g_fail = 0;
static void check(bool ok, const char* w) { std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", w); if (!ok) ++g_fail; }
static unsigned short g_port;
static int dial() {
    const int c0 = probe::connected.load();
    int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in sa{}; sa.sin_family = AF_INET; sa.sin_port = htons(g_port); sa.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (::connect(fd, (sockaddr*)&sa, sizeof sa) != 0) { std::perror("connect"); std::exit(2); }
    auto d = std::chrono::steady_clock::now() + 3s;
    while (probe::connected.load() == c0 && std::chrono::steady_clock::now() < d) std::this_thread::sleep_for(1ms);
    return fd;
}
static void sendl(int fd, const std::string& s) { ::send(fd, s.data(), s.size(), MSG_NOSIGNAL); }
struct RR { std::vector<std::string> lines; bool eof = false; };
// Pump drain() and read until EOF or `total`.
static RR pump(int fd, std::chrono::milliseconds total, const std::function<void()>& per_tick = {}) {
    RR r; std::string buf; auto d = std::chrono::steady_clock::now() + total;
    while (std::chrono::steady_clock::now() < d) {
        if (per_tick) per_tick();
        kp::harness::drain();
        pollfd p{fd, POLLIN, 0};
        if (::poll(&p, 1, 5) > 0) {
            char t[8192]; ssize_t g = ::recv(fd, t, sizeof t, 0);
            if (g <= 0) { r.eof = true; break; }
            buf.append(t, (size_t)g);
        }
    }
    size_t s = 0, nl; while ((nl = buf.find('\n', s)) != std::string::npos) { r.lines.push_back(buf.substr(s, nl - s)); s = nl + 1; }
    if (s < buf.size()) r.lines.push_back(buf.substr(s) + "<no-nl>");
    return r;
}
static int count(const RR& r, const char* needle) { int n = 0; for (auto& l : r.lines) if (l.find(needle) != std::string::npos) ++n; return n; }
static void dump(const char* tag, const RR& r) { for (auto& l : r.lines) std::printf("    %s: %s\n", tag, l.c_str()); std::printf("    %s: eof=%d\n", tag, r.eof); }
static void subscribe(int fd) {
    sendl(fd, "{\"id\":1,\"cmd\":\"subscribe\"}\n");
    RR r = pump(fd, 150ms); dump("sub", r);
}
int main() {
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    std::string err; kp::harness::HarnessOptions o;
    if (!kp::harness::start(o, err)) { std::printf("start failed %s\n", err.c_str()); return 2; }
    g_port = kp::harness::listening_port();
    auto& ring = kp::harness::ring();

    std::printf("-- A: healthy subscriber gets events (control)\n");
    { int fd = dial(); subscribe(fd);
      ring.push("r2.control", 1);
      RR r = pump(fd, 150ms); dump("A", r);
      check(count(r, "r2.control") == 1 && !r.eof, "A healthy subscriber receives event, stays open");
      ::close(fd); for (int i=0;i<10;++i){kp::harness::drain(); std::this_thread::sleep_for(5ms);} }

    std::printf("-- B: subscribed client sends bad line; event already in ring and events pushed every tick\n");
    { int fd = dial(); subscribe(fd);
      ring.push("r2.before_bad", 2);
      sendl(fd, "{bad\n");
      RR r = pump(fd, 400ms, [&] { ring.push("r2.after_bad", 3); });
      dump("B", r);
      int errs = 0; for (auto& l : r.lines) if (l.find("\"ok\":false") != std::string::npos) ++errs;
      check(errs == 1, "B exactly one error line");
      size_t ei = r.lines.size(); for (size_t i = 0; i < r.lines.size(); ++i) if (r.lines[i].find("\"ok\":false") != std::string::npos) { ei = i; break; }
      check(ei + 1 == r.lines.size(), "B the error is the last line (nothing follows it)");
      check(r.eof, "B connection closed");
      ::close(fd); for (int i=0;i<10;++i){kp::harness::drain(); std::this_thread::sleep_for(5ms);} }

    std::printf("-- C: fresh client after a condemn is not poisoned; subscribes, gets events and replies\n");
    { int fd = dial(); subscribe(fd);
      ring.push("r2.fresh", 4);
      RR r = pump(fd, 200ms);
      sendl(fd, "{\"id\":7,\"cmd\":\"subscribe\"}\n");
      RR r2 = pump(fd, 200ms); for (auto& l : r2.lines) r.lines.push_back(l); r.eof = r.eof || r2.eof; dump("C", r);
      check(count(r, "r2.fresh") == 1, "C fresh client gets event");
      check(count(r, "\"id\":7") == 1, "C fresh client gets reply");
      check(!r.eof, "C fresh client stays open");
      ::close(fd); for (int i=0;i<10;++i){kp::harness::drain(); std::this_thread::sleep_for(5ms);} }

    std::printf("-- D: good request then bad line in one send: good reply + error, then EOF\n");
    { int fd = dial();
      sendl(fd, "{\"id\":9,\"cmd\":\"subscribe\"}\n{bad\n{\"id\":10,\"cmd\":\"subscribe\"}\n");
      RR r = pump(fd, 300ms); dump("D", r);
      check(count(r, "\"id\":9") == 1, "D good reply before bad line delivered");
      check(count(r, "\"id\":10") == 0, "D request after bad line not answered");
      check(r.lines.size() == 2 && r.eof, "D exactly two lines then EOF");
      ::close(fd); for (int i=0;i<10;++i){kp::harness::drain(); std::this_thread::sleep_for(5ms);} }

    kp::harness::stop();
    std::printf("%d failure(s)\n", g_fail);
    return g_fail ? 1 : 0;
}
