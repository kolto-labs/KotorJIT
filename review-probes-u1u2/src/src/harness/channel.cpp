// The control channel's listener thread. See channel.hpp for the contract.
#include "harness/channel.hpp"

#include <chrono>
#include <cstring>
#include <utility>

#if defined(_WIN32)
// winsock2 before windows.h, or windows.h drags in the old winsock and the two
// headers fight over every symbol.
#include <winsock2.h>
#include <ws2tcpip.h>
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <arpa/inet.h>
#include <cerrno>
#include <fcntl.h>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

#include "platform/platform.hpp"

namespace kp::harness {
namespace {

#if defined(_WIN32)
using sock_t = SOCKET;
constexpr sock_t kInvalidSock = INVALID_SOCKET;
void close_sock(sock_t s) { ::closesocket(s); }
bool set_nonblocking(sock_t s) {
    u_long on = 1;
    return ::ioctlsocket(s, FIONBIO, &on) == 0;
}
int last_error() { return ::WSAGetLastError(); }
bool would_block(int e) { return e == WSAEWOULDBLOCK; }
#else
using sock_t = int;
constexpr sock_t kInvalidSock = -1;
void close_sock(sock_t s) { ::close(s); }
bool set_nonblocking(sock_t s) {
    const int flags = ::fcntl(s, F_GETFL, 0);
    return flags >= 0 && ::fcntl(s, F_SETFL, flags | O_NONBLOCK) == 0;
}
int last_error() { return errno; }
bool would_block(int e) { return e == EWOULDBLOCK || e == EAGAIN; }
#endif

// send() must never raise SIGPIPE: the peer can go away between select() and
// send(), and the default disposition would kill the game rather than fail the
// write. Winsock has no such signal and no such flag.
#if defined(_WIN32)
constexpr int kSendFlags = 0;
#else
constexpr int kSendFlags = MSG_NOSIGNAL;
#endif

// select() indexes fd_set by descriptor on POSIX, so a descriptor at or above
// FD_SETSIZE would write past the set. Winsock's fd_set is an array of handles
// with its own count, so the descriptor value does not matter there.
#if defined(_WIN32)
bool fd_in_select_range(sock_t) { return true; }
#else
bool fd_in_select_range(sock_t s) { return s >= 0 && s < FD_SETSIZE; }
#endif

// A line longer than this is not a request anyone typed. The connection is
// closed rather than the line truncated: a truncated request could parse as
// a different, valid one.
constexpr std::size_t kMaxLine = 1u << 20;

// Queue ceilings. A client that sends without reading would otherwise grow
// both queues without limit; past these the connection is dropped with a
// logged reason, because the alternative is the game running out of memory.
constexpr std::size_t kMaxQueuedRequests = 4096;
constexpr std::size_t kMaxQueuedBytes    = 8u << 20;
constexpr std::size_t kMaxQueuedReplies  = 4096;
constexpr std::size_t kMaxOutBytes       = 8u << 20;

// How long select() waits before checking for queued replies and the stop
// flag. Replies therefore leave within this bound of being queued; the client
// loop runs at frame rate, so this is not what bounds latency.
constexpr long kSelectWaitUs = 5000;

const char kBusyLine[] = "{\"ok\":false,\"error\":\"busy: another client is connected\"}\n";
const char kTooLongLine[] = "{\"ok\":false,\"error\":\"line too long; connection closed\"}\n";
const char kNoRoomLine[] =
    "{\"ok\":false,\"error\":\"refused: descriptor at or above FD_SETSIZE\"}\n";

bool is_loopback(const std::string& bind, in_addr& out) {
    const std::string text = bind == "localhost" ? std::string("127.0.0.1") : bind;
    const unsigned long raw = ::inet_addr(text.c_str());
    if (raw == INADDR_NONE) return false;
    out.s_addr = static_cast<decltype(out.s_addr)>(raw);
    return (ntohl(static_cast<std::uint32_t>(raw)) >> 24) == 127;
}

}  // namespace

LineShape screen_request_line(const std::string& line) {
    std::size_t i = 0;
    while (i < line.size() && (line[i] == ' ' || line[i] == '\t' || line[i] == '\r')) ++i;
    if (i < line.size() && line[i] == '{') return LineShape::Ok;
    // Wording only: anything that does not open an object is refused anyway.
    static const char* const kMethods[] = {"GET ",     "POST ",  "PUT ",     "HEAD ", "OPTIONS ",
                                           "DELETE ",  "PATCH ", "CONNECT ", "TRACE "};
    for (const char* m : kMethods)
        if (line.compare(i, std::strlen(m), m) == 0) return LineShape::Http;
    if (line.find("HTTP/1.") != std::string::npos || line.find("HTTP/2") != std::string::npos)
        return LineShape::Http;
    return LineShape::NotObject;
}

Channel::Channel() = default;

Channel::~Channel() { stop(); }

bool Channel::start(const ChannelOptions& opts, std::string& error) {
    if (running()) { error = "channel already running"; return false; }

    in_addr addr{};
    if (!is_loopback(opts.bind, addr)) {
        error = "refusing to bind " + opts.bind + ": the harness listens on loopback only";
        return false;
    }

#if defined(_WIN32)
    WSADATA wsa;
    if (::WSAStartup(MAKEWORD(2, 2), &wsa) != 0) {
        error = "WSAStartup failed";
        return false;
    }
#endif

    sock_t s = ::socket(AF_INET, SOCK_STREAM, 0);
    if (s == kInvalidSock) {
        error = "socket() failed, error " + std::to_string(last_error());
#if defined(_WIN32)
        ::WSACleanup();
#endif
        return false;
    }
    if (!fd_in_select_range(s)) {
        error = "listen descriptor " + std::to_string(static_cast<long long>(s)) +
                " is at or above FD_SETSIZE; the harness cannot select() on it";
        close_sock(s);
#if defined(_WIN32)
        ::WSACleanup();
#endif
        return false;
    }

    // Reuse so a restart right after a crash does not wait out TIME_WAIT.
    int one = 1;
    ::setsockopt(s, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<const char*>(&one), sizeof one);

    sockaddr_in sa{};
    sa.sin_family = AF_INET;
    sa.sin_addr = addr;
    sa.sin_port = htons(opts.port);
    if (::bind(s, reinterpret_cast<const sockaddr*>(&sa), sizeof sa) != 0) {
        error = "bind " + opts.bind + ":" + std::to_string(opts.port) + " failed, error " +
                std::to_string(last_error());
        close_sock(s);
#if defined(_WIN32)
        ::WSACleanup();
#endif
        return false;
    }
    if (::listen(s, 4) != 0) {
        error = "listen failed, error " + std::to_string(last_error());
        close_sock(s);
#if defined(_WIN32)
        ::WSACleanup();
#endif
        return false;
    }

    sockaddr_in bound{};
    socklen_t len = sizeof bound;
    if (::getsockname(s, reinterpret_cast<sockaddr*>(&bound), &len) == 0)
        port_ = ntohs(bound.sin_port);
    else
        port_ = opts.port;

    // A blocking listener would make accept() and the busy reply able to hold
    // the thread, and stop() then blocks in join(). Refuse to start instead.
    if (!set_nonblocking(s)) {
        error = "cannot put the listen socket in non-blocking mode, error " +
                std::to_string(last_error());
        close_sock(s);
#if defined(_WIN32)
        ::WSACleanup();
#endif
        return false;
    }
    listen_sock_ = static_cast<std::intptr_t>(s);
    overflow_.store(false, std::memory_order_release);
    outbuf_pending_.store(0, std::memory_order_release);
    stop_.store(false, std::memory_order_release);
    running_.store(true, std::memory_order_release);
    thread_ = std::thread([this] { run(); });
    return true;
}

void Channel::stop() {
    if (!running()) return;
    stop_.store(true, std::memory_order_release);
    if (thread_.joinable()) thread_.join();

    close_client();
    if (listen_sock_ != -1) {
        close_sock(static_cast<sock_t>(listen_sock_));
        listen_sock_ = -1;
    }
    {
        std::lock_guard<std::mutex> lock(mutex_);
        requests_.clear();
        replies_.clear();
        request_bytes_ = 0;
        reply_bytes_ = 0;
    }
    running_.store(false, std::memory_order_release);
#if defined(_WIN32)
    ::WSACleanup();
#endif
}

void Channel::close_client() {
    if (client_sock_ != -1) {
        close_sock(static_cast<sock_t>(client_sock_));
        client_sock_ = -1;
    }
    client_gen_.store(0, std::memory_order_release);
    subscribed_.store(false, std::memory_order_release);
    inbuf_.clear();
    outbuf_.clear();
    outbuf_pending_.store(0, std::memory_order_release);
    overflow_.store(false, std::memory_order_release);
    std::lock_guard<std::mutex> lock(mutex_);
    // Requests not yet taken belonged to the client that just left. Replies
    // still queued would be delivered to nobody; push_reply filters the rest.
    requests_.clear();
    replies_.clear();
    request_bytes_ = 0;
    reply_bytes_ = 0;
}

std::size_t Channel::take_requests(std::size_t max, std::vector<Request>& out) {
    std::lock_guard<std::mutex> lock(mutex_);
    const std::size_t n = requests_.size() < max ? requests_.size() : max;
    for (std::size_t i = 0; i < n; ++i) {
        const std::size_t bytes = requests_[i].line.size();
        request_bytes_ -= request_bytes_ < bytes ? request_bytes_ : bytes;
        out.push_back(std::move(requests_[i]));
    }
    requests_.erase(requests_.begin(), requests_.begin() + static_cast<std::ptrdiff_t>(n));
    return n;
}

void Channel::push_reply(std::uint64_t client, std::string line) {
    if (client == 0 || client != current_client()) return;
    std::lock_guard<std::mutex> lock(mutex_);
    // Over the ceiling the reply is refused rather than queued: the client is
    // not reading, and the listener closes the connection on the flag.
    if (replies_.size() >= kMaxQueuedReplies || reply_bytes_ + line.size() > kMaxQueuedBytes) {
        overflow_.store(true, std::memory_order_release);
        return;
    }
    reply_bytes_ += line.size();
    replies_.push_back({client, std::move(line)});
}

std::size_t Channel::pending_requests() {
    std::lock_guard<std::mutex> lock(mutex_);
    return requests_.size();
}

std::size_t Channel::pending_replies() {
    std::lock_guard<std::mutex> lock(mutex_);
    return replies_.size();
}

bool Channel::wait_flushed(unsigned timeout_ms) {
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
    while (std::chrono::steady_clock::now() < deadline) {
        if (!client_connected() || !running()) return true;
        bool empty;
        {
            std::lock_guard<std::mutex> lock(mutex_);
            empty = replies_.empty();
        }
        // Both halves have to be empty. The reply queue drains into outbuf_
        // before the socket is even selected, so a queue that has just gone
        // empty says nothing about whether the bytes left: the listener
        // publishes outbuf_'s size after every append and every send, and that
        // is the half this reads. outbuf_ itself stays the listener's own.
        empty = empty && outbuf_pending_.load(std::memory_order_acquire) == 0;
        if (empty) {
            std::this_thread::sleep_for(std::chrono::microseconds(2 * kSelectWaitUs));
            return true;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    return false;
}

void Channel::run() {
    // Nothing that fails inside the loop may leave this thread: an allocation
    // or a logging failure escaping run() would call std::terminate and take
    // the game with it. A failure here costs the connection, never the process.
    try {
        run_loop();
    } catch (...) {
        close_client();
        try {
            platform::log(platform::LogLevel::Warn,
                          "harness: listener hit an allocation or I/O failure; client dropped");
        } catch (...) {
        }
    }
}

void Channel::run_loop() {
    const sock_t ls = static_cast<sock_t>(listen_sock_);

    while (!stop_.load(std::memory_order_acquire)) {
        const sock_t cs = static_cast<sock_t>(client_sock_);
        const bool have_client = cs != kInvalidSock && client_sock_ != -1;

        if (have_client && overflow_.load(std::memory_order_acquire)) {
            platform::log(platform::LogLevel::Warn,
                          "harness: reply queue over %zu lines or %zu bytes; client dropped",
                          kMaxQueuedReplies, kMaxQueuedBytes);
            close_client();
            continue;
        }

        // Read before the reply pull. The main thread condemns a client only
        // after pushing its error reply, so a condemnation seen here means
        // the pull below already holds that reply.
        const bool doomed = have_client &&
                            condemned_gen_.load(std::memory_order_acquire) ==
                                client_gen_.load(std::memory_order_acquire);

        // Pull queued replies into the write buffer before selecting, so a
        // reply queued while we waited goes out on this round.
        if (have_client) {
            std::lock_guard<std::mutex> lock(mutex_);
            const std::uint64_t gen = client_gen_.load(std::memory_order_acquire);
            for (Reply& r : replies_) {
                if (r.client != gen) continue;
                outbuf_ += r.line;
                outbuf_.push_back('\n');
            }
            replies_.clear();
            reply_bytes_ = 0;
            outbuf_pending_.store(outbuf_.size(), std::memory_order_release);
        }

        // A condemned client gets what was queued for it, in one non-blocking
        // write, and is closed. Nothing it sent after the bad line runs: the
        // drain's admit() refuses the generation, and close_client() drops
        // whatever the listener still held.
        if (doomed) {
            if (!outbuf_.empty())
                ::send(cs, outbuf_.data(), static_cast<int>(outbuf_.size()), kSendFlags);
            platform::log(platform::LogLevel::Warn,
                          "harness: client sent a line that is not a JSON request; client dropped");
            close_client();
            continue;
        }

        if (have_client && outbuf_.size() > kMaxOutBytes) {
            platform::log(platform::LogLevel::Warn,
                          "harness: unsent replies over %zu bytes; client dropped", kMaxOutBytes);
            close_client();
            continue;
        }

        fd_set readable;
        fd_set writable;
        FD_ZERO(&readable);
        FD_ZERO(&writable);
        FD_SET(ls, &readable);
        int maxfd = static_cast<int>(ls);
        if (have_client) {
            FD_SET(cs, &readable);
            if (!outbuf_.empty()) FD_SET(cs, &writable);
            if (static_cast<int>(cs) > maxfd) maxfd = static_cast<int>(cs);
        }

        timeval tv{};
        tv.tv_sec = 0;
        tv.tv_usec = kSelectWaitUs;
        const int n = ::select(maxfd + 1, &readable, &writable, nullptr, &tv);
        if (n <= 0) continue;

        if (FD_ISSET(ls, &readable)) {
            sockaddr_in peer{};
            socklen_t plen = sizeof peer;
            const sock_t a = ::accept(ls, reinterpret_cast<sockaddr*>(&peer), &plen);
            if (a != kInvalidSock) {
                if (have_client || !fd_in_select_range(a)) {
                    const bool no_room = !fd_in_select_range(a);
                    // Refused, not queued: a driver that connects twice must
                    // learn it at once, not when the first session ends. The
                    // socket is put in non-blocking mode first, so a peer that
                    // never reads cannot hold the listener in send(); one
                    // partial write is all this line is worth.
                    if (no_room)
                        platform::log(platform::LogLevel::Warn,
                                      "harness: refusing a descriptor at or above FD_SETSIZE");
                    set_nonblocking(a);
                    const char* line = no_room ? kNoRoomLine : kBusyLine;
                    const std::size_t len = no_room ? sizeof kNoRoomLine - 1 : sizeof kBusyLine - 1;
                    ::send(a, line, static_cast<int>(len), kSendFlags);
                    close_sock(a);
                } else if (!set_nonblocking(a)) {
                    platform::log(platform::LogLevel::Warn,
                                  "harness: cannot put the client socket in non-blocking mode; refused");
                    close_sock(a);
                } else {
                    int one = 1;
                    ::setsockopt(a, IPPROTO_TCP, TCP_NODELAY,
                                 reinterpret_cast<const char*>(&one), sizeof one);
                    client_sock_ = static_cast<std::intptr_t>(a);
                    inbuf_.clear();
                    outbuf_.clear();
                    outbuf_pending_.store(0, std::memory_order_release);
                    overflow_.store(false, std::memory_order_release);
                    subscribed_.store(false, std::memory_order_release);
                    client_gen_.store(next_gen_++, std::memory_order_release);
                    accepted_.fetch_add(1, std::memory_order_acq_rel);
                    platform::log(platform::LogLevel::Info, "harness: client connected");
                    continue;   // re-select with the new socket in the set
                }
            }
        }

        if (!have_client) continue;

        if (FD_ISSET(cs, &readable)) {
            char buf[4096];
            const int got = ::recv(cs, buf, sizeof buf, 0);
            if (got == 0 || (got < 0 && !would_block(last_error()))) {
                platform::log(platform::LogLevel::Info, "harness: client disconnected");
                close_client();
                continue;
            }
            if (got > 0) {
                inbuf_.append(buf, static_cast<std::size_t>(got));
                const std::uint64_t gen = client_gen_.load(std::memory_order_acquire);
                std::size_t start = 0;
                bool too_many = false;
                while (true) {
                    const std::size_t nl = inbuf_.find('\n', start);
                    if (nl == std::string::npos) break;
                    std::size_t end = nl;
                    if (end > start && inbuf_[end - 1] == '\r') --end;
                    if (end > start) {
                        std::lock_guard<std::mutex> lock(mutex_);
                        // A client that sends faster than the drain answers is
                        // dropped at the ceiling rather than queued forever.
                        if (requests_.size() >= kMaxQueuedRequests ||
                            request_bytes_ + (end - start) > kMaxQueuedBytes) {
                            too_many = true;
                            break;
                        }
                        request_bytes_ += end - start;
                        requests_.push_back({gen, inbuf_.substr(start, end - start)});
                    }
                    start = nl + 1;
                }
                inbuf_.erase(0, start);
                if (too_many) {
                    platform::log(platform::LogLevel::Warn,
                                  "harness: request queue over %zu lines or %zu bytes; client dropped",
                                  kMaxQueuedRequests, kMaxQueuedBytes);
                    close_client();
                    continue;
                }
                if (inbuf_.size() > kMaxLine) {
                    ::send(cs, kTooLongLine, static_cast<int>(sizeof kTooLongLine - 1), kSendFlags);
                    platform::log(platform::LogLevel::Warn,
                                  "harness: line over %zu bytes; client dropped", kMaxLine);
                    close_client();
                    continue;
                }
            }
        }

        if (FD_ISSET(cs, &writable) && !outbuf_.empty()) {
            const int sent = ::send(cs, outbuf_.data(), static_cast<int>(outbuf_.size()), kSendFlags);
            if (sent > 0) {
                outbuf_.erase(0, static_cast<std::size_t>(sent));
                outbuf_pending_.store(outbuf_.size(), std::memory_order_release);
            } else if (sent < 0 && !would_block(last_error())) {
                platform::log(platform::LogLevel::Info, "harness: client write failed; dropped");
                close_client();
            }
        }
    }
}

}  // namespace kp::harness
