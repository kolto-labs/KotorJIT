#include "api/engine_gate.hpp"
#include <thread>
static bool probe(void*) { return true; }
int main() {
    std::thread t([]{ kp::api::engine::bind_gate(probe, nullptr); });
    t.join();
    return kp::api::engine::on_engine_thread() ? 0 : 1;
}
