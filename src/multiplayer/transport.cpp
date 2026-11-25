#include "multiplayer/transport.hpp"

#include <algorithm>
#include <array>
#include <cstring>
#include <utility>

#if defined(_WIN32)
#include <winsock2.h>
#include <ws2tcpip.h>
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

namespace kp::multiplayer {
namespace {

#if defined(_WIN32)
using sock_t = SOCKET;
constexpr sock_t kInvalidSocket = INVALID_SOCKET;
void close_socket(sock_t socket) { ::closesocket(socket); }
int socket_error() { return ::WSAGetLastError(); }
bool would_block(int error) { return error == WSAEWOULDBLOCK; }
bool set_nonblocking(sock_t socket) {
    u_long enabled = 1;
    return ::ioctlsocket(socket, FIONBIO, &enabled) == 0;
}
#else
using sock_t = int;
constexpr sock_t kInvalidSocket = -1;
void close_socket(sock_t socket) { ::close(socket); }
int socket_error() { return errno; }
bool would_block(int error) { return error == EWOULDBLOCK || error == EAGAIN; }
bool set_nonblocking(sock_t socket) {
    const int flags = ::fcntl(socket, F_GETFL, 0);
    return flags >= 0 && ::fcntl(socket, F_SETFL, flags | O_NONBLOCK) == 0;
}
#endif

#if defined(_WIN32) || defined(__APPLE__)
constexpr int kSendFlags = 0;
#else
constexpr int kSendFlags = MSG_NOSIGNAL;
#endif

void suppress_sigpipe(sock_t s) {
#if defined(__APPLE__)
    int one = 1;
    ::setsockopt(s, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof one);
#else
    (void)s;
#endif
}

constexpr std::array<std::uint8_t, 4> kMagic{'K', 'P', 'M', 'P'};
constexpr std::uint16_t kVersion = 2;
constexpr std::size_t kHeaderBytes = 16;
constexpr std::uint16_t kHelloFrame = 0;
constexpr std::uint16_t kDataFrame = 1;
constexpr std::size_t kMaxCompatibilityBytes = 128;
constexpr std::size_t kMaxQueuedFrames = 1024;
constexpr std::size_t kMaxQueuedBytes = 4u << 20;
constexpr std::size_t kIoChunk = 4096;
constexpr long kSelectWaitUs = 5000;

bool socket_fits_select(sock_t socket) {
#if defined(_WIN32)
    (void)socket;
    return true;
#else
    return socket >= 0 && socket < FD_SETSIZE;
#endif
}

bool loopback_address(const std::string& text, in_addr& result) {
    const std::string address = text == "localhost" ? "127.0.0.1" : text;
    const unsigned long raw = ::inet_addr(address.c_str());
    if (raw == INADDR_NONE) return false;
    result.s_addr = static_cast<decltype(result.s_addr)>(raw);
    return (ntohl(static_cast<std::uint32_t>(raw)) >> 24) == 127;
}

void put_u16(std::vector<std::uint8_t>& out, std::uint16_t value) {
    out.push_back(static_cast<std::uint8_t>(value >> 8));
    out.push_back(static_cast<std::uint8_t>(value));
}

void put_u32(std::vector<std::uint8_t>& out, std::uint32_t value) {
    out.push_back(static_cast<std::uint8_t>(value >> 24));
    out.push_back(static_cast<std::uint8_t>(value >> 16));
    out.push_back(static_cast<std::uint8_t>(value >> 8));
    out.push_back(static_cast<std::uint8_t>(value));
}

std::uint16_t get_u16(const std::uint8_t* in) {
    return static_cast<std::uint16_t>((static_cast<std::uint16_t>(in[0]) << 8) | in[1]);
}

std::uint32_t get_u32(const std::uint8_t* in) {
    return (static_cast<std::uint32_t>(in[0]) << 24) |
           (static_cast<std::uint32_t>(in[1]) << 16) |
           (static_cast<std::uint32_t>(in[2]) << 8) |
           static_cast<std::uint32_t>(in[3]);
}

}  // namespace

Transport::Transport() = default;
Transport::~Transport() { stop(); }

bool Transport::start_network(std::string& error) {
#if defined(_WIN32)
    WSADATA data{};
    if (::WSAStartup(MAKEWORD(2, 2), &data) != 0) {
        error = "WSAStartup failed";
        return false;
    }
#else
    (void)error;
#endif
    network_started_ = true;
    return true;
}

bool Transport::start_server(std::string bind, std::uint16_t port, std::string compatibility,
                             std::string& error) {
    if (running() || thread_.joinable()) { error = "transport already started"; return false; }
    if (compatibility.empty() || compatibility.size() > kMaxCompatibilityBytes) {
        error = "compatibility identity must be 1..128 bytes";
        return false;
    }
    in_addr address{};
    if (!loopback_address(bind, address)) {
        error = "refusing non-loopback bind " + bind;
        return false;
    }
    if (!start_network(error)) return false;

    const sock_t listener = ::socket(AF_INET, SOCK_STREAM, 0);
    if (listener == kInvalidSocket || !socket_fits_select(listener)) {
        error = "cannot create selectable listen socket, error " + std::to_string(socket_error());
        if (listener != kInvalidSocket) close_socket(listener);
        stop();
        return false;
    }
    int one = 1;
    ::setsockopt(listener, SOL_SOCKET, SO_REUSEADDR,
                 reinterpret_cast<const char*>(&one), sizeof one);
    sockaddr_in endpoint{};
    endpoint.sin_family = AF_INET;
    endpoint.sin_addr = address;
    endpoint.sin_port = htons(port);
    if (::bind(listener, reinterpret_cast<const sockaddr*>(&endpoint), sizeof endpoint) != 0 ||
        ::listen(listener, 1) != 0 || !set_nonblocking(listener)) {
        error = "cannot bind/listen on " + bind + ":" + std::to_string(port) +
                ", error " + std::to_string(socket_error());
        close_socket(listener);
        stop();
        return false;
    }
    sockaddr_in bound{};
#if defined(_WIN32)
    int length = sizeof bound;
#else
    socklen_t length = sizeof bound;
#endif
    if (::getsockname(listener, reinterpret_cast<sockaddr*>(&bound), &length) != 0) {
        error = "getsockname failed, error " + std::to_string(socket_error());
        close_socket(listener);
        stop();
        return false;
    }
    role_ = Role::Server;
    compatibility_ = std::move(compatibility);
    port_ = ntohs(bound.sin_port);
    listen_sock_ = static_cast<std::intptr_t>(listener);
    stop_.store(false, std::memory_order_release);
    running_.store(true, std::memory_order_release);
    thread_ = std::thread([this] { run(); });
    return true;
}

bool Transport::start_client(std::string host, std::uint16_t port, std::string compatibility,
                             std::string& error) {
    if (running() || thread_.joinable()) { error = "transport already started"; return false; }
    if (compatibility.empty() || compatibility.size() > kMaxCompatibilityBytes) {
        error = "compatibility identity must be 1..128 bytes";
        return false;
    }
    in_addr address{};
    if (!loopback_address(host, address)) {
        error = "refusing non-loopback peer " + host;
        return false;
    }
    if (!start_network(error)) return false;
    const sock_t connection = ::socket(AF_INET, SOCK_STREAM, 0);
    if (connection == kInvalidSocket || !socket_fits_select(connection)) {
        error = "cannot create selectable client socket, error " + std::to_string(socket_error());
        if (connection != kInvalidSocket) close_socket(connection);
        stop();
        return false;
    }
    sockaddr_in endpoint{};
    endpoint.sin_family = AF_INET;
    endpoint.sin_addr = address;
    endpoint.sin_port = htons(port);
    if (::connect(connection, reinterpret_cast<const sockaddr*>(&endpoint), sizeof endpoint) != 0) {
        error = "connect to " + host + ":" + std::to_string(port) + " failed, error " +
                std::to_string(socket_error());
        close_socket(connection);
        stop();
        return false;
    }
    if (!set_nonblocking(connection)) {
        error = "cannot make client socket nonblocking, error " + std::to_string(socket_error());
        close_socket(connection);
        stop();
        return false;
    }
    int one = 1;
    suppress_sigpipe(connection);
    ::setsockopt(connection, IPPROTO_TCP, TCP_NODELAY,
                 reinterpret_cast<const char*>(&one), sizeof one);
    role_ = Role::Client;
    compatibility_ = std::move(compatibility);
    port_ = port;
    connection_sock_ = static_cast<std::intptr_t>(connection);
    connected_.store(false, std::memory_order_release);
    stop_.store(false, std::memory_order_release);
    running_.store(true, std::memory_order_release);
    thread_ = std::thread([this] { run(); });
    return true;
}

void Transport::stop() {
    stop_.store(true, std::memory_order_release);
    if (thread_.joinable()) thread_.join();
    close_connection();
    if (listen_sock_ != -1) {
        close_socket(static_cast<sock_t>(listen_sock_));
        listen_sock_ = -1;
    }
    running_.store(false, std::memory_order_release);
    role_ = Role::None;
    compatibility_.clear();
    port_ = 0;
#if defined(_WIN32)
    if (network_started_) ::WSACleanup();
#endif
    network_started_ = false;
}

bool Transport::send(std::span<const std::uint8_t> payload, std::uint32_t player,
                     std::uint32_t extra, FrameKind kind) {
    if (payload.size() > kMaxFrameBytes || !connected()) return false;
    std::lock_guard<std::mutex> lock(mutex_);
    if (outgoing_.size() >= kMaxQueuedFrames ||
        outgoing_bytes_ + payload.size() > kMaxQueuedBytes) return false;
    outgoing_.push_back({role_ == Role::Server ? FrameSender::Server : FrameSender::Client,
                         kind, player, extra, {payload.begin(), payload.end()}});
    outgoing_bytes_ += payload.size();
    return true;
}

std::size_t Transport::take_frames(std::size_t max, std::vector<Frame>& out) {
    std::lock_guard<std::mutex> lock(mutex_);
    const std::size_t count = std::min(max, incoming_.size());
    for (std::size_t i = 0; i < count; ++i) {
        incoming_bytes_ -= incoming_.front().payload.size();
        out.push_back(std::move(incoming_.front()));
        incoming_.pop_front();
    }
    return count;
}

void Transport::close_connection() {
    if (connection_sock_ != -1) {
        close_socket(static_cast<sock_t>(connection_sock_));
        connection_sock_ = -1;
    }
    connected_.store(false, std::memory_order_release);
    input_.clear();
    output_.clear();
    output_offset_ = 0;
    hello_sent_ = false;
    peer_ready_ = false;
    send_sequence_ = 1;
    receive_sequence_ = 1;
    std::lock_guard<std::mutex> lock(mutex_);
    outgoing_.clear();
    incoming_.clear();
    outgoing_bytes_ = 0;
    incoming_bytes_ = 0;
}

bool Transport::parse_input() {
    while (input_.size() >= kHeaderBytes) {
        if (!std::equal(kMagic.begin(), kMagic.end(), input_.begin()) ||
            get_u16(input_.data() + 4) != kVersion) return false;
        const std::uint16_t kind = get_u16(input_.data() + 6);
        const std::size_t length = get_u32(input_.data() + 8);
        const std::uint32_t sequence = get_u32(input_.data() + 12);
        if (length > kMaxFrameBytes + 8) return false;
        if (input_.size() < kHeaderBytes + length) return true;

        std::vector<std::uint8_t> payload(input_.begin() + kHeaderBytes,
                                          input_.begin() + kHeaderBytes + length);
        if (kind == kHelloFrame) {
            if (peer_ready_ || sequence != 0 ||
                payload.size() != compatibility_.size() ||
                !std::equal(payload.begin(), payload.end(), compatibility_.begin())) return false;
            peer_ready_ = true;
            connected_.store(true, std::memory_order_release);
        } else if (kind == kDataFrame ||
                   kind == static_cast<std::uint16_t>(FrameKind::MoveToPoint) ||
                   kind == static_cast<std::uint16_t>(FrameKind::AuthoritativePosition)) {
            if (!peer_ready_ || sequence != receive_sequence_++ || payload.size() < 8) return false;
            const std::uint32_t player = get_u32(payload.data());
            const std::uint32_t extra = get_u32(payload.data() + 4);
            payload.erase(payload.begin(), payload.begin() + 8);
            if (payload.size() > kMaxFrameBytes) return false;
            std::lock_guard<std::mutex> lock(mutex_);
            if (incoming_.size() >= kMaxQueuedFrames ||
                incoming_bytes_ + payload.size() > kMaxQueuedBytes) return false;
            incoming_bytes_ += payload.size();
            incoming_.push_back({role_ == Role::Server ? FrameSender::Client : FrameSender::Server,
                                 static_cast<FrameKind>(kind), player, extra, std::move(payload)});
        } else return false;
        input_.erase(input_.begin(), input_.begin() + kHeaderBytes + length);
    }
    return true;
}

void Transport::run() {
    try {
        run_loop();
    } catch (...) {
        close_connection();
    }
    running_.store(false, std::memory_order_release);
}

void Transport::run_loop() {
    while (!stop_.load(std::memory_order_acquire)) {
        sock_t connection = connection_sock_ == -1
            ? kInvalidSocket : static_cast<sock_t>(connection_sock_);

        if (connection != kInvalidSocket && output_.empty()) {
            std::vector<std::uint8_t> hello;
            std::lock_guard<std::mutex> lock(mutex_);
            const bool sending_hello = !hello_sent_;
            if (sending_hello) hello.assign(compatibility_.begin(), compatibility_.end());
            if (sending_hello || !outgoing_.empty()) {
                const std::vector<std::uint8_t>& payload = sending_hello
                    ? hello : outgoing_.front().payload;
                const std::size_t metadata_bytes = sending_hello ? 0 : 8;
                output_.reserve(kHeaderBytes + metadata_bytes + payload.size());
                output_.insert(output_.end(), kMagic.begin(), kMagic.end());
                put_u16(output_, kVersion);
                put_u16(output_, sending_hello ? kHelloFrame
                                               : static_cast<std::uint16_t>(outgoing_.front().kind));
                put_u32(output_, static_cast<std::uint32_t>(metadata_bytes + payload.size()));
                put_u32(output_, sending_hello ? 0 : send_sequence_++);
                if (!sending_hello) {
                    put_u32(output_, outgoing_.front().player);
                    put_u32(output_, outgoing_.front().extra);
                }
                output_.insert(output_.end(), payload.begin(), payload.end());
                if (sending_hello) hello_sent_ = true;
                else {
                    outgoing_bytes_ -= payload.size();
                    outgoing_.pop_front();
                }
                output_offset_ = 0;
            }
        }

        fd_set readable;
        fd_set writable;
        FD_ZERO(&readable);
        FD_ZERO(&writable);
        int maxfd = -1;
        const sock_t listener = listen_sock_ == -1
            ? kInvalidSocket : static_cast<sock_t>(listen_sock_);
        if (listener != kInvalidSocket) {
            FD_SET(listener, &readable);
            maxfd = static_cast<int>(listener);
        }
        if (connection != kInvalidSocket) {
            FD_SET(connection, &readable);
            if (!output_.empty()) FD_SET(connection, &writable);
            maxfd = std::max(maxfd, static_cast<int>(connection));
        }
        if (maxfd < 0) break;

        timeval timeout{};
        timeout.tv_usec = kSelectWaitUs;
        const int selected = ::select(maxfd + 1, &readable, &writable, nullptr, &timeout);
        if (selected < 0) break;

        if (listener != kInvalidSocket && FD_ISSET(listener, &readable)) {
            sockaddr_in peer{};
#if defined(_WIN32)
            int length = sizeof peer;
#else
            socklen_t length = sizeof peer;
#endif
            const sock_t accepted = ::accept(listener, reinterpret_cast<sockaddr*>(&peer), &length);
            if (accepted != kInvalidSocket) {
                if (connection != kInvalidSocket || !socket_fits_select(accepted) ||
                    (ntohl(peer.sin_addr.s_addr) >> 24) != 127 || !set_nonblocking(accepted)) {
                    close_socket(accepted);
                } else {
                    int one = 1;
                    suppress_sigpipe(accepted);
                    ::setsockopt(accepted, IPPROTO_TCP, TCP_NODELAY,
                                 reinterpret_cast<const char*>(&one), sizeof one);
                    connection_sock_ = static_cast<std::intptr_t>(accepted);
                    hello_sent_ = false;
                    peer_ready_ = false;
                    send_sequence_ = 1;
                    receive_sequence_ = 1;
                    connected_.store(false, std::memory_order_release);
                    connection = accepted;
                }
            }
        }

        if (connection == kInvalidSocket) continue;
        if (FD_ISSET(connection, &readable)) {
            std::array<std::uint8_t, kIoChunk> buffer{};
            const int received = ::recv(connection, reinterpret_cast<char*>(buffer.data()),
                                        static_cast<int>(buffer.size()), 0);
            if (received == 0 || (received < 0 && !would_block(socket_error()))) {
                close_connection();
                if (role_ == Role::Client) break;
                continue;
            }
            if (received > 0) {
                input_.insert(input_.end(), buffer.begin(), buffer.begin() + received);
                if (!parse_input()) {
                    close_connection();
                    if (role_ == Role::Client) break;
                    continue;
                }
            }
        }
        if (connection_sock_ == -1) continue;
        if (FD_ISSET(connection, &writable) && !output_.empty()) {
            const std::size_t remaining = output_.size() - output_offset_;
            const std::size_t chunk = std::min(remaining, kIoChunk);
            const int sent = ::send(connection,
                                    reinterpret_cast<const char*>(output_.data() + output_offset_),
                                    static_cast<int>(chunk), kSendFlags);
            if (sent > 0) {
                output_offset_ += static_cast<std::size_t>(sent);
                if (output_offset_ == output_.size()) {
                    output_.clear();
                    output_offset_ = 0;
                }
            } else if (sent < 0 && !would_block(socket_error())) {
                close_connection();
                if (role_ == Role::Client) break;
            }
        }
    }
}

}  // namespace kp::multiplayer
