// Security review probe: the public Channel API only.  It demonstrates what
// happens to a reply queued *after* condemn(), while the condemned generation
// is still connected.  This is the path used by stream_events()/deferred work.
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <cstdio>
#include <string>
#include <thread>

#include "harness/channel.hpp"

int main() {
    kp::harness::Channel ch;
    kp::harness::ChannelOptions opts;
    std::string error;
    if (!ch.start(opts, error)) { std::printf("start failed: %s\n", error.c_str()); return 2; }
    int fd = ::socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in sa{};
    sa.sin_family = AF_INET;
    sa.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    sa.sin_port = htons(ch.port());
    if (::connect(fd, reinterpret_cast<sockaddr*>(&sa), sizeof sa) != 0) return 3;
    for (int i = 0; i != 1000 && !ch.client_connected(); ++i)
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    const std::uint64_t gen = ch.current_client();
    ch.push_reply(gen, "{\"error\":\"first\"}");
    ch.condemn(gen);
    ch.push_reply(gen, "{\"secret\":\"post-condemn reply\"}");
    char buf[512]{};
    const int n = static_cast<int>(::recv(fd, buf, sizeof buf - 1, 0));
    std::printf("generation=%llu bytes=%d payload=%.*s\n", static_cast<unsigned long long>(gen), n, n > 0 ? n : 0, buf);
    ::close(fd);
    ch.stop();
    return n > 0 && std::string(buf, static_cast<std::size_t>(n)).find("post-condemn reply") != std::string::npos ? 1 : 0;
}
