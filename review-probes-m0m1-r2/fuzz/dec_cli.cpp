// Reads hex lines, prints "len rel rel_offset ends_flow" per line (len 0 = refused).
#include "hooks/x64/decode.hpp"
#include <cstdio>
#include <cstring>
#include <string>
#include <iostream>
using namespace kp::hooks::x64;
int main() {
    std::string line;
    while (std::getline(std::cin, line)) {
        unsigned char b[64]; size_t n = 0;
        for (size_t i = 0; i + 1 < line.size() && n < 64; i += 2)
            b[n++] = (unsigned char)std::stoi(line.substr(i, 2), nullptr, 16);
        auto in = decode(b, n);
        std::printf("%u %u %u %u %s\n", in.len, (unsigned)in.rel, in.rel_offset, in.ends_flow ? 1 : 0,
                    in.refusal ? "R" : "-");
    }
}
