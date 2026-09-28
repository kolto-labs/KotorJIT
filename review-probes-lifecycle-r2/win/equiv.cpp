// Does libstdc++-on-mingw fs::equivalent compare real file ids under Wine?
#include <cstdio>
#include <filesystem>
#include <fstream>
namespace fs = std::filesystem;
int main(int, char** argv) {
    fs::path d = argv[1];
    std::error_code ec; fs::remove_all(d, ec); fs::create_directories(d);
    { std::ofstream(d / "a.lua") << "x"; }
    { std::ofstream(d / "c.lua") << "x"; }
    fs::create_hard_link(d / "a.lua", d / "b.lua", ec);
    std::printf("hardlink create: %s\n", ec ? ec.message().c_str() : "ok");
    auto eq = [&](const char* x, const char* y) {
        std::error_code e; bool r = fs::equivalent(d / x, d / y, e);
        std::printf("equivalent(%s,%s)=%d ec=%s\n", x, y, int(r), e ? e.message().c_str() : "-");
    };
    eq("a.lua", "a.lua"); eq("a.lua", "A.LUA"); eq("a.lua", "b.lua"); eq("a.lua", "c.lua");
    std::printf("exists(A.LUA)=%d\n", int(fs::exists(d / "A.LUA")));
    for (auto& e : fs::directory_iterator(d)) std::printf("listed %s\n", e.path().string().c_str());
    std::printf("lexically_normal(%s)=%s\n", "Z:/x/./y/a.lua", fs::path("Z:/x/./y/a.lua").lexically_normal().string().c_str());
    return 0;
}
