// Offline regression for the production commands.cpp drain and stream_events
// path.  The test uses a real loopback Channel and the process-wide EventRing;
// it never starts the game or Wine.  The kotorjit shared library supplies the
// typed runtime/API dependencies while commands.cpp is compiled afresh into
// this executable, so this target cannot silently fall back to a retained
// commands.o from an earlier review.

#include <arpa/inet.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <netinet/in.h>
#include <poll.h>
#include <string>
#include <sys/socket.h>
#include <thread>
#include <vector>
#include <unistd.h>

#include "harness/commands.hpp"
#include "harness/ring.hpp"

using namespace std::chrono_literals;
using kp::harness::EventRing;

namespace {

struct Receipt {
    std::vector<std::string> lines;
    bool eof = false;
};

int failures = 0;

void check(bool ok, const char* what) {
    std::printf("  [%s] %s\n", ok ? "PASS" : "FAIL", what);
    if (!ok) ++failures;
}

void send_line(int fd, const char* text) {
    const std::string line(text);
    const ssize_t n = ::send(fd, line.data(), line.size(), MSG_NOSIGNAL);
    check(n == static_cast<ssize_t>(line.size()), "request line sent");
}

Receipt pump(int fd, std::chrono::milliseconds limit,
             const std::function<void()>& per_tick = {}) {
    Receipt out;
    std::string bytes;
    const auto deadline = std::chrono::steady_clock::now() + limit;
    while (std::chrono::steady_clock::now() < deadline) {
        if (per_tick) per_tick();
        kp::harness::drain();
        pollfd p{fd, POLLIN, 0};
        if (::poll(&p, 1, 5) > 0) {
            char buf[8192];
            const ssize_t n = ::recv(fd, buf, sizeof buf, 0);
            if (n <= 0) {
                out.eof = true;
                break;
            }
            bytes.append(buf, static_cast<std::size_t>(n));
        }
    }
    std::size_t start = 0;
    for (;;) {
        const std::size_t end = bytes.find('\n', start);
        if (end == std::string::npos) break;
        out.lines.push_back(bytes.substr(start, end - start));
        start = end + 1;
    }
    if (start < bytes.size()) out.lines.push_back(bytes.substr(start) + "<no-nl>");
    return out;
}

int lines_containing(const Receipt& r, const char* needle) {
    int count = 0;
    for (const std::string& line : r.lines)
        if (line.find(needle) != std::string::npos) ++count;
    return count;
}

int connect_client(unsigned short port) {
    const int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    if (fd < 0) return -1;
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
    address.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (::connect(fd, reinterpret_cast<sockaddr*>(&address), sizeof address) != 0) {
        ::close(fd);
        return -1;
    }
    return fd;
}

void drain_after_close() {
    for (int i = 0; i < 10; ++i) {
        kp::harness::drain();
        std::this_thread::sleep_for(5ms);
    }
}

void subscribe(int fd) {
    send_line(fd, "{\"id\":1,\"cmd\":\"subscribe\"}\n");
    const Receipt r = pump(fd, 150ms);
    check(lines_containing(r, "\"id\":1") == 1, "subscribe reply delivered");
    check(!r.eof, "subscribed client remains open");
}

void real_drain_cases(unsigned short port) {
    EventRing& events = kp::harness::ring();

    std::printf("-- healthy subscribed client receives a ring event\n");
    {
        const int fd = connect_client(port);
        check(fd >= 0, "healthy client connects");
        subscribe(fd);
        events.push("h0.control", 1);
        const Receipt r = pump(fd, 150ms);
        check(lines_containing(r, "h0.control") == 1 && !r.eof,
              "healthy subscriber receives event and stays open");
        ::close(fd);
        drain_after_close();
    }

    std::printf("-- malformed line condemns client; stream_events must not leak a later event\n");
    {
        const int fd = connect_client(port);
        check(fd >= 0, "condemned client connects");
        subscribe(fd);
        events.push("h0.before_bad", 2);
        send_line(fd, "{bad\n");
        const Receipt r = pump(fd, 400ms, [&] { events.push("h0.after_bad", 3); });
        int errors = 0;
        std::size_t error_index = r.lines.size();
        for (std::size_t i = 0; i < r.lines.size(); ++i) {
            if (r.lines[i].find("\"ok\":false") != std::string::npos) {
                ++errors;
                if (error_index == r.lines.size()) error_index = i;
            }
        }
        check(errors == 1, "condemned client receives exactly one error");
        check(error_index + 1 == r.lines.size(),
              "the error is the final line; no post-condemn event follows");
        check(r.eof, "condemned client is closed");
        ::close(fd);
        drain_after_close();
    }

    std::printf("-- a reconnect gets a fresh stream after the condemned generation closes\n");
    {
        const int fd = connect_client(port);
        check(fd >= 0, "reconnected client connects");
        subscribe(fd);
        events.push("h0.reconnect", 4);
        const Receipt r = pump(fd, 150ms);
        check(lines_containing(r, "h0.reconnect") == 1 && !r.eof,
              "reconnected subscriber receives its event and stays open");
        ::close(fd);
        drain_after_close();
    }

    std::printf("-- good request before a bad line survives in the same batch\n");
    {
        const int fd = connect_client(port);
        check(fd >= 0, "same-batch client connects");
        send_line(fd, "{\"id\":9,\"cmd\":\"subscribe\"}\n{bad\n{\"id\":10,\"cmd\":\"subscribe\"}\n");
        const Receipt r = pump(fd, 300ms);
        check(lines_containing(r, "\"id\":9") == 1,
              "good reply before malformed line is delivered");
        check(lines_containing(r, "\"id\":10") == 0,
              "request after malformed line is not executed");
        check(r.lines.size() == 2 && r.eof, "same-batch client gets two lines then EOF");
        ::close(fd);
        drain_after_close();
    }
}

}  // namespace

int main() {
    std::setvbuf(stdout, nullptr, _IOLBF, 0);
    kp::harness::HarnessOptions options;
    std::string error;
    if (!kp::harness::start(options, error)) {
        std::printf("start failed: %s\n", error.c_str());
        return 2;
    }
    real_drain_cases(kp::harness::listening_port());
    kp::harness::stop();
    std::printf("%d failure(s)\n", failures);
    return failures == 0 ? 0 : 1;
}
