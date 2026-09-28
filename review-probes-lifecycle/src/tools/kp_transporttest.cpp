#include "multiplayer/transport.hpp"

#include <chrono>
#include <cstdint>
#include <iostream>
#include <thread>
#include <vector>

namespace {

using kp::multiplayer::Frame;
using kp::multiplayer::FrameSender;
using kp::multiplayer::Transport;

bool wait_connected(const Transport& endpoint) {
    for (int i = 0; i < 400; ++i) {
        if (endpoint.connected()) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    return false;
}

bool wait_frame(Transport& endpoint, Frame& frame) {
    for (int i = 0; i < 400; ++i) {
        std::vector<Frame> frames;
        endpoint.take_frames(1, frames);
        if (!frames.empty()) {
            frame = std::move(frames.front());
            return true;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    return false;
}

int fail(const char* message) {
    std::cerr << "FAIL: " << message << '\n';
    return 1;
}

}  // namespace

int main() {
    Transport server;
    Transport client;
    std::string error;
    if (!server.start_server("127.0.0.1", 0, "fixture-sha256", error)) {
        std::cerr << "FAIL: server start: " << error << '\n';
        return 1;
    }
    if (!client.start_client("127.0.0.1", server.port(), "fixture-sha256", error)) {
        std::cerr << "FAIL: client start: " << error << '\n';
        return 1;
    }
    if (!wait_connected(server) || !wait_connected(client)) return fail("connection timeout");

    const std::vector<std::uint8_t> client_payload{0x41, 0x00, 0x42, 0xff, 0x00};
    if (!client.send(client_payload, 0xfffffffdu, 0x12345678u,
                     kp::multiplayer::FrameKind::MoveToPoint))
        return fail("client enqueue rejected");
    Frame received{};
    if (!wait_frame(server, received) || received.sender != FrameSender::Client ||
        received.kind != kp::multiplayer::FrameKind::MoveToPoint ||
        received.player != 0xfffffffdu || received.extra != 0x12345678u ||
        received.payload != client_payload) return fail("client-to-server frame mismatch");

    const std::vector<std::uint8_t> position_payload(16, 0x5a);
    if (!server.send(position_payload, 0, 0,
                     kp::multiplayer::FrameKind::AuthoritativePosition))
        return fail("position acknowledgment enqueue rejected");
    if (!wait_frame(client, received) || received.sender != FrameSender::Server ||
        received.kind != kp::multiplayer::FrameKind::AuthoritativePosition ||
        received.payload != position_payload)
        return fail("server-to-client position acknowledgment mismatch");

    // Larger than the transport's individual send()/recv() chunk, making the
    // self-test deterministically exercise frame assembly across partial I/O.
    std::vector<std::uint8_t> server_payload(kp::multiplayer::kMaxFrameBytes);
    for (std::size_t i = 0; i < server_payload.size(); ++i)
        server_payload[i] = static_cast<std::uint8_t>((i * 37u) & 0xffu);
    server_payload[1] = 0;
    server_payload[server_payload.size() - 2] = 0;
    if (!server.send(server_payload)) return fail("server enqueue rejected");
    if (!wait_frame(client, received) || received.sender != FrameSender::Server ||
        received.payload != server_payload) return fail("server-to-client partial frame mismatch");

    const std::vector<std::uint8_t> oversized(kp::multiplayer::kMaxFrameBytes + 1);
    if (client.send(oversized)) return fail("oversized frame accepted");
    if (!client.connected() || !server.connected()) return fail("oversize rejection dropped connection");

    client.stop();
    server.stop();

    if (!server.start_server("127.0.0.1", 0, "server-build", error) ||
        !client.start_client("127.0.0.1", server.port(), "client-build", error))
        return fail("mismatch fixture start failed");
    for (int i = 0; i < 400 && client.running(); ++i) {
        if (client.connected() || server.connected()) return fail("mismatched builds connected");
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    if (client.connected() || server.connected()) return fail("mismatched builds connected");
    client.stop();
    server.stop();

    std::cout << "OK: binary frames with selectors, partial I/O, bounds, build mismatch rejection\n";
    return 0;
}
