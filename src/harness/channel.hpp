// The control channel: a loopback TCP listener that never touches the engine.
//
// One thread does socket / bind / listen / accept and then select() over the
// listen socket and the one client. It splits what arrives into lines and
// queues them; it writes what the main thread queued back. It never parses a
// request, never reads engine memory, never sees a lua_State. Parsing happens
// on the main thread under the fault guard, and execution happens there too,
// because that is the only thread on which engine calls are legal.
//
// One client at a time. A second connection gets one JSON error line and is
// closed, so "who is driving" is never ambiguous. Every request carries the
// client generation it arrived on; a reply for a client that has since gone
// is dropped rather than delivered to whoever connected next.
//
// Loopback only. A bind address outside 127.0.0.0/8 is refused at start(),
// not narrowed: the harness runs unauthenticated Lua in the game's process.
//
// Wine's ws2_32 maps AF_INET onto host sockets, so this same file serves the
// DLL under Wine and the native Linux build; only the includes differ.
#pragma once

#include <atomic>
#include <cstddef>
#include <cstdint>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace kp::harness {

struct ChannelOptions {
    std::string    bind = "127.0.0.1";
    unsigned short port = 0;      // 0: any free port; read it back with port()
};

struct Request {
    std::uint64_t client = 0;     // generation of the connection it came from
    std::string   line;           // one complete line, newline stripped
};

class Channel {
public:
    Channel();
    ~Channel();

    Channel(const Channel&) = delete;
    Channel& operator=(const Channel&) = delete;

    bool start(const ChannelOptions&, std::string& error);
    void stop();

    bool           running() const { return running_.load(std::memory_order_acquire); }
    unsigned short port() const { return port_; }

    // ---- main-thread side ----

    // Move up to `max` queued requests into `out`, oldest first. Called before
    // any fault guard is armed: it takes the queue mutex, and a claimed fault
    // runs no destructors, so a mutex held inside the guard would deadlock the
    // listener forever.
    std::size_t take_requests(std::size_t max, std::vector<Request>& out);

    // Queue one line for the client `client`. Dropped when that client is no
    // longer the connected one. The listener appends the newline.
    void push_reply(std::uint64_t client, std::string line);

    // Generation of the connected client, or 0 when nobody is connected.
    std::uint64_t current_client() const { return client_gen_.load(std::memory_order_acquire); }
    bool client_connected() const { return current_client() != 0; }

    // Event streaming flag. Set by `subscribe`, cleared by `unsubscribe` and
    // by every new connection, so a fresh client never inherits a stream.
    void set_subscribed(bool on) { subscribed_.store(on, std::memory_order_release); }
    bool subscribed() const { return subscribed_.load(std::memory_order_acquire); }

    // Block until every queued reply has been handed to the socket, the client
    // has gone, or `timeout_ms` passed. For `quit`: the reply must leave
    // before the client loop returns the exit flag.
    bool wait_flushed(unsigned timeout_ms);

    std::size_t pending_requests();
    std::size_t pending_replies();

    // Connections accepted so far, and lines dropped for being longer than the
    // limit. Diagnostics for `status` and the self-test.
    std::uint64_t accepted_count() const { return accepted_.load(std::memory_order_acquire); }

private:
    struct Reply {
        std::uint64_t client;
        std::string   line;
    };

    void run();        // the thread body: contains any failure at the boundary
    void run_loop();   // the select loop itself
    void close_client();

    std::thread        thread_;
    std::atomic<bool>  running_{false};
    std::atomic<bool>  stop_{false};
    std::atomic<bool>  subscribed_{false};
    std::atomic<std::uint64_t> client_gen_{0};
    std::atomic<std::uint64_t> accepted_{0};
    unsigned short     port_ = 0;

    // Opaque so the header carries no socket type; the .cpp knows which.
    std::intptr_t listen_sock_ = -1;
    std::intptr_t client_sock_ = -1;
    std::uint64_t next_gen_ = 1;

    std::mutex           mutex_;
    std::vector<Request> requests_;
    std::vector<Reply>   replies_;
    std::size_t          request_bytes_ = 0;   // both under mutex_
    std::size_t          reply_bytes_ = 0;

    // Set when a queue ceiling was passed. The main thread can only refuse a
    // reply; the listener is the one that closes the connection, so the reason
    // is raised here and acted on there.
    std::atomic<bool> overflow_{false};

    // Listener-thread-only buffers. `outbuf_pending_` mirrors outbuf_.size()
    // so wait_flushed can see the bytes that left the reply queue but have not
    // reached the socket, without taking the buffer away from its one thread.
    std::string inbuf_;
    std::string outbuf_;
    std::atomic<std::size_t> outbuf_pending_{0};
};

}  // namespace kp::harness
