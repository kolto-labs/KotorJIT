// Platform bits that are the same everywhere: the log sink and its default.
//
// Kept out of the per-OS files so that adding a third platform does not mean
// re-implementing message formatting for a third time.

#include "platform/platform.hpp"

#include <cstdarg>
#include <cstdio>

namespace kp::platform {
namespace {

LogSink g_sink = nullptr;
void*   g_sink_user = nullptr;

// stderr rather than stdout: the tool prints its results on stdout, and a log
// line interleaved into those results would make the evidence harder to read.
void default_sink(LogLevel level, const char* message, void*) {
    std::fprintf(stderr, "[kp:%s] %s\n", to_string(level), message);
}

}  // namespace

const char* to_string(LogLevel level) {
    switch (level) {
        case LogLevel::Debug: return "debug";
        case LogLevel::Info:  return "info";
        case LogLevel::Warn:  return "warn";
        case LogLevel::Error: return "error";
    }
    return "?";
}

void set_log_sink(LogSink sink, void* user) {
    g_sink = sink;
    g_sink_user = user;
}

void log(LogLevel level, const char* fmt, ...) {
    // A fixed buffer, deliberately. This is called from inside hook bodies on
    // the game's own threads, where an allocation is a bad idea and a failed
    // allocation is a worse one. Truncation is the acceptable failure mode.
    char buffer[512];
    std::va_list args;
    va_start(args, fmt);
    std::vsnprintf(buffer, sizeof(buffer), fmt, args);
    va_end(args);

    if (g_sink) {
        g_sink(level, buffer, g_sink_user);
    } else {
        default_sink(level, buffer, nullptr);
    }
}

}  // namespace kp::platform
