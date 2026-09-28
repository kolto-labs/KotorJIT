#include "api/engine_gate.hpp"
#include <thread>
int main(){
  kp::api::engine::bind_gate(nullptr,nullptr);
  std::thread t([]{ kp::api::engine::bind_gate(nullptr,nullptr); });
  t.join();
  return kp::api::engine::on_engine_thread()?1:0;
}
