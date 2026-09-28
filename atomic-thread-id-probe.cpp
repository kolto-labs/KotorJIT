#include <atomic>
#include <thread>
#include <cstdio>
int main(){
  unsigned failures=0;
  for(unsigned n=0;n<1000;++n){
    std::atomic<std::thread::id> owner{};
    auto main=std::this_thread::get_id();
    std::thread::id zero{};
    bool first=owner.compare_exchange_strong(zero,main,std::memory_order_acq_rel);
    bool replaced=false;
    std::thread worker([&]{std::thread::id unset{};replaced=owner.compare_exchange_strong(unset,std::this_thread::get_id(),std::memory_order_acq_rel);});
    worker.join();
    if(!first||replaced||owner.load()!=main)++failures;
  }
  std::printf("atomic thread id size=%zu alignment=%zu failures=%u / 1000\n",sizeof(std::thread::id),alignof(std::thread::id),failures);
  return failures?1:0;
}
