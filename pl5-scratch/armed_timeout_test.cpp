#include "armed_timeout.hpp"
#include <cassert>
#include <chrono>
#include <iostream>

int main() {
    using namespace std::chrono;
    using kp::harness::pause::snippet::armed_expired;
    const auto start = steady_clock::now();
    assert(!armed_expired(start + 59s, start));
    assert(armed_expired(start + 60s, start));
    assert(!armed_expired(start, {}));
    int end_load = 0;
    bool loading = true;
    if (armed_expired(start + 60s, start)) {
        ++end_load;
        loading = false;
    }
    if (armed_expired(start + 61s, {})) ++end_load;
    assert(end_load == 1 && !loading);
    std::cout << "armed timeout: 60s; terminal end_load calls=1; loading=false; later frame calls=0\n";
}
