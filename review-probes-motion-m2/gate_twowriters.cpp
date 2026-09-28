// Review probe: two concurrent binders. The header says bind_gate is "Safe to
// call from any thread"; a seqlock with fetch_add from two writers can return
// to an even count while both are mid-write.
#include "api/engine_gate.hpp"
#include <atomic>
#include <cstdio>
#include <thread>
using namespace kp::api::engine;
std::atomic<long> torn{0}, asked{0};
bool yes_probe(void* c){ if(c!=(void*)0x1) torn++; return true; }
bool no_probe(void* c){ if(c!=(void*)0x2) torn++; return false; }
int main(int argc,char**argv){
  long iters = argc>1?atol(argv[1]):2000000;
  std::atomic<bool> stop{false};
  std::thread r1([&]{ while(!stop){ (void)on_engine_thread(); asked++; } });
  std::thread r2([&]{ while(!stop){ (void)on_engine_thread(); asked++; } });
  std::thread a([&]{ for(long i=0;i<iters;++i) bind_gate(yes_probe,(void*)0x1); });
  std::thread b([&]{ for(long i=0;i<iters;++i) bind_gate(no_probe,(void*)0x2); });
  a.join(); b.join(); stop=true; r1.join(); r2.join();
  std::printf("two writers: iters=%ld asked=%ld torn=%ld\n", iters, asked.load(), torn.load());
  return torn? 1:0;
}
