#include "events/situation.hpp"

#include <fstream>
#include <iterator>

namespace kp::events {

bool write_situation_blob(const std::string& path, std::string_view blob) {
    if (path.empty()) return false;
    std::ofstream out(path, std::ios::binary | std::ios::trunc);
    if (!out) return false;
    out.write(blob.data(), static_cast<std::streamsize>(blob.size()));
    return static_cast<bool>(out);
}

std::string read_situation_blob(const std::string& path) {
    if (path.empty()) return {};
    std::ifstream in(path, std::ios::binary);
    if (!in) return {};
    return std::string((std::istreambuf_iterator<char>(in)),
                       std::istreambuf_iterator<char>());
}

}  // namespace kp::events
