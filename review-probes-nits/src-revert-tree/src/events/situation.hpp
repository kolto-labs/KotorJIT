// Sidecar next to a save: the string OnSave claimed, read back by OnLoad.
#pragma once

#include <string>
#include <string_view>

namespace kp::events {

bool        write_situation_blob(const std::string& path, std::string_view blob);
std::string read_situation_blob(const std::string& path);

}  // namespace kp::events
