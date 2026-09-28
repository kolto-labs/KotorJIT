#pragma once

#include <string_view>

namespace kp::multiplayer {

enum class Role { Embedded, Client, Server };

constexpr Role role_from_executable(std::string_view path) {
    const std::size_t slash = path.find_last_of("/\\");
    const std::string_view name = slash == std::string_view::npos ? path : path.substr(slash + 1);
    return name.ends_with("-server.exe") || name.ends_with("-server.elf")
        ? Role::Server
        : name.ends_with("-client.exe") || name.ends_with("-client.elf")
            ? Role::Client
            : Role::Embedded;
}

constexpr const char* to_string(Role role) {
    switch (role) {
        case Role::Embedded: return "embedded";
        case Role::Client:   return "client";
        case Role::Server:   return "server";
    }
    return "embedded";
}

static_assert(role_from_executable(R"(C:\Games\swkotor-server.exe)") == Role::Server);
static_assert(role_from_executable("/game/swkotor-client.exe") == Role::Client);
static_assert(role_from_executable("/game/swkotor.exe") == Role::Embedded);

}  // namespace kp::multiplayer
