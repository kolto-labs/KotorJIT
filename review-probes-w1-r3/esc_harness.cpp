// Harness: the escape loop copied verbatim (sed by line number) from Runtime::log.
#include <cstdio>
#include <cstddef>
#include <string>
#include <iostream>
#include <iterator>
int main(int argc, char** argv) {
    // argv[1] = phase; stdin = the message (the vsnprintf result, <=1023 bytes)
    std::string in((std::istreambuf_iterator<char>(std::cin)), std::istreambuf_iterator<char>());
    char raw[1024];
    std::snprintf(raw, sizeof raw, "%s", in.c_str());
    char body[4 * sizeof raw];
    std::size_t n = 0;
    for (const char* p = raw; *p != '\0'; ++p) {
        const unsigned char c = static_cast<unsigned char>(*p);
        if (c >= 0x20 && c != 0x7f) {
            body[n++] = *p;
            continue;
        }
        body[n++] = '\\';
        switch (c) {
            case '\n': body[n++] = 'n'; break;
            case '\r': body[n++] = 'r'; break;
            case '\t': body[n++] = 't'; break;
            default:
                body[n++] = 'x';
                body[n++] = "0123456789abcdef"[c >> 4];
                body[n++] = "0123456789abcdef"[c & 0x0f];
                break;
        }
    }
    body[n] = '\0';
    std::printf("[%s] %s\n", argv[1], body);
    return 0;
}
