// Engine-thread gate (src/api/engine_gate.*) offline tests. Host-only.
// The thread-latch probe below exists only in this test; the runtime binds its
// own probe (live() && current thread == latched server MainLoop thread).
#include "api/engine_gate.hpp"
#include <atomic>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <string>
#include <thread>
using namespace kp::api::engine;
#define CHECK(x) do{if(!(x))throw std::runtime_error(std::string("line ")+std::to_string(__LINE__)+": "+#x);}while(0)

namespace {
unsigned checks=0;
#define COUNT(x) do{CHECK(x);++checks;}while(0)
bool flag_probe(void* c){return *static_cast<bool*>(c);}
unsigned probe_calls=0;
bool counting_probe(void* c){++probe_calls;return *static_cast<bool*>(c);}

void unbound_refuses(){
 bind_gate(nullptr,nullptr);
 COUNT(!on_engine_thread());
 COUNT(std::strcmp(gate_refusal(),"unsupported: not on the engine thread")==0);
 // A context with no probe is still unbound.
 bool yes=true;bind_gate(nullptr,&yes);COUNT(!on_engine_thread());
}

void bound_probe_true_allows(){
 bool flag=true;bind_gate(flag_probe,&flag);
 COUNT(on_engine_thread());
 flag=false;COUNT(!on_engine_thread());   // the probe is asked every time
 flag=true;COUNT(on_engine_thread());
 probe_calls=0;bind_gate(counting_probe,&flag);
 COUNT(on_engine_thread());COUNT(on_engine_thread());COUNT(probe_calls==2);
 bind_gate(nullptr,nullptr);
}

void rebind_nullptr_refuses(){
 bool flag=true;bind_gate(flag_probe,&flag);COUNT(on_engine_thread());
 bind_gate(nullptr,nullptr);COUNT(!on_engine_thread());
 // Rebinding to a different context uses the new context, not the old one.
 bool no=false;bind_gate(flag_probe,&flag);bind_gate(flag_probe,&no);COUNT(!on_engine_thread());
 bind_gate(nullptr,nullptr);
}

// The shape the runtime uses: a latched thread id. The latch is set once by
// the "engine" thread; every other thread, and every thread before the latch,
// is refused.
struct Latch{std::atomic<bool> set{false};std::thread::id id;std::atomic<bool> live{true};};
bool latch_probe(void* c){
 auto* l=static_cast<Latch*>(c);
 return l->live.load()&&l->set.load()&&std::this_thread::get_id()==l->id;
}
void other_thread_refused(){
 Latch latch;bind_gate(latch_probe,&latch);
 COUNT(!on_engine_thread());               // before the latch: refused
 latch.id=std::this_thread::get_id();latch.set=true;
 COUNT(on_engine_thread());
 bool other=true;
 std::thread t([&]{other=on_engine_thread();});t.join();
 COUNT(!other);                            // a real second thread is refused
 latch.live=false;COUNT(!on_engine_thread()); // runtime not live: refused on the latched thread too
 bind_gate(nullptr,nullptr);
}

// Hammer bind/unbind from one thread while another asks. The asker must only
// ever see true while the "yes" probe is bound; a torn (probe, context) pair
// would call flag_probe with the "no" context or vice versa. Here both pairs
// agree with the probe, so any mismatch is caught by the probe itself.
bool yes_probe(void* c){if(c!=reinterpret_cast<void*>(0x1))throw std::runtime_error("torn pair: yes probe got a foreign context");return true;}
bool no_probe(void* c){if(c!=reinterpret_cast<void*>(0x2))throw std::runtime_error("torn pair: no probe got a foreign context");return false;}
void concurrent_rebind_never_tears(){
 std::atomic<bool> stop{false};std::atomic<bool> torn{false};
 std::thread asker([&]{
  while(!stop.load()){try{(void)on_engine_thread();}catch(...){torn=true;}}
 });
 for(int i=0;i<200000;++i){
  bind_gate(yes_probe,reinterpret_cast<void*>(0x1));
  bind_gate(no_probe,reinterpret_cast<void*>(0x2));
  if(i%3==0)bind_gate(nullptr,nullptr);
 }
 stop=true;asker.join();
 COUNT(!torn.load());
 bind_gate(nullptr,nullptr);COUNT(!on_engine_thread());
}
} // namespace

int main(){
 struct T{const char* name;void(*fn)();};
 const T tests[]={
  {"engine_gate.unbound_refuses",unbound_refuses},
  {"engine_gate.bound_probe_true_allows",bound_probe_true_allows},
  {"engine_gate.rebind_nullptr_refuses",rebind_nullptr_refuses},
  {"engine_gate.other_thread_refused",other_thread_refused},
  {"engine_gate.concurrent_rebind_never_tears",concurrent_rebind_never_tears},
 };
 unsigned failed=0;
 for(const auto& t:tests){
  try{t.fn();std::cout<<"PASS "<<t.name<<"\n";}
  catch(const std::exception& e){++failed;std::cout<<"FAIL "<<t.name<<": "<<e.what()<<"\n";}
  bind_gate(nullptr,nullptr);
 }
 std::cout<<(sizeof(tests)/sizeof(tests[0])-failed)<<"/"<<sizeof(tests)/sizeof(tests[0])<<" tests passed, "<<checks<<" checks\n";
 return failed?1:0;
}
