#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <mutex>
#include <span>
#include <string>
#include <thread>
#include <vector>

namespace kp::multiplayer {

inline constexpr std::size_t kMaxFrameBytes = 65536;

enum class FrameSender { Client, Server };
enum class FrameKind : std::uint16_t {
    Engine = 1,
    MoveToPoint = 2,
    AuthoritativePosition = 3,
};

struct Frame {
    FrameSender sender;
    FrameKind kind = FrameKind::Engine;
    std::uint32_t player = 0;
    std::uint32_t extra = 0;
    std::vector<std::uint8_t> payload;
};

// One loopback-only connection. The socket thread only moves opaque frames;
// engine work belongs to the thread that drains take_frames().
class Transport {
public:
    Transport();
    ~Transport();

    Transport(const Transport&) = delete;
    Transport& operator=(const Transport&) = delete;

    bool start_server(std::string bind, std::uint16_t port, std::string compatibility,
                      std::string& error);
    bool start_client(std::string host, std::uint16_t port, std::string compatibility,
                      std::string& error);
    void stop();

    bool running() const { return running_.load(std::memory_order_acquire); }
    bool connected() const { return connected_.load(std::memory_order_acquire); }
    std::uint16_t port() const { return port_; }

    bool send(std::span<const std::uint8_t> payload, std::uint32_t player = 0,
              std::uint32_t extra = 0, FrameKind kind = FrameKind::Engine);
    std::size_t take_frames(std::size_t max, std::vector<Frame>& out);

private:
    enum class Role { None, Server, Client };

    bool start_network(std::string& error);
    bool parse_input();
    void close_connection();
    void run();
    void run_loop();

    Role role_ = Role::None;
    std::thread thread_;
    std::atomic<bool> running_{false};
    std::atomic<bool> stop_{false};
    std::atomic<bool> connected_{false};
    bool network_started_ = false;
    std::uint16_t port_ = 0;
    std::string compatibility_;
    std::intptr_t listen_sock_ = -1;
    std::intptr_t connection_sock_ = -1;

    std::mutex mutex_;
    std::deque<Frame> outgoing_;
    std::deque<Frame> incoming_;
    std::size_t outgoing_bytes_ = 0;
    std::size_t incoming_bytes_ = 0;

    std::vector<std::uint8_t> input_;
    std::vector<std::uint8_t> output_;
    std::size_t output_offset_ = 0;
    bool hello_sent_ = false;
    bool peer_ready_ = false;
    std::uint32_t send_sequence_ = 1;
    std::uint32_t receive_sequence_ = 1;
};

}  // namespace kp::multiplayer
