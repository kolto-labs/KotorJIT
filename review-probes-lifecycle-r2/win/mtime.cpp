// mtime resolution seen by libstdc++ fs::last_write_time in this build.
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <thread>
namespace fs = std::filesystem;
int main(int, char** argv) {
    fs::path d = argv[1]; std::error_code ec; fs::create_directories(d, ec);
    unsigned same = 0, n = 20; long long nonzero_subsec = 0;
    for (unsigned i = 0; i < n; ++i) {
        { std::ofstream(d / "m.lua") << "a" << i; }
        auto t1 = fs::last_write_time(d / "m.lua");
        std::this_thread::sleep_for(std::chrono::milliseconds(150));
        { std::ofstream(d / "m.lua") << "b" << i; }
        auto t2 = fs::last_write_time(d / "m.lua");
        if (t1 == t2) ++same;
        auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(t2.time_since_epoch()).count();
        if (ns % 1000000000LL) ++nonzero_subsec;
    }
    std::printf("writes 150ms apart with equal mtime: %u/%u; stamps with sub-second part: %lld/%u\n", same, n, nonzero_subsec, n);
    return 0;
}
