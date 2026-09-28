#include "api/projectiles_profile.hpp"
namespace kp::api::projectiles {
// Exact original-PE verification, 2026-09-22. ABI/caller evidence in the
// projectile visual report; unsupported images never call these addresses.
const Profile &profile() {
  static const Profile p{
      "9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435",
      "windows-k1-gog-i386",
      0x400000,
      0x7a39fc,
      0x7a39e8,
      0x7a3a28,
      0x757cc8,
      0x650554,
      {{{0x6d2c50, "6aff68cb5e730064a100000000506489", 3},
        {0x650543, "6a0068ff0000008d442434508bceff527885c0", -1},
        {0x408bc0, "518d44240c508b4424108d542404528b", -1},
        {0x406d80, "8b44240483ec10568bf1508d4c240851", -1},
        {0x5e5a90, "56578b7c240c85ff8bf174458bc78d50", -1},
        {0x5e5c20, "568bf18b0685c0741650c74604000000", -1},
        {0x413270, "8b442408535657508bf1e881feffff8b", -1},
        {0x4aea40, "8b4904e9686200009090909090909090", -1},
        {0x5eda50, "8b4904e9685000009090909090909090", -1},
        {0x5ed5b0, "8b4904e9c83b00009090909090909090", -1}}}};
  return p;
}
} // namespace kp::api::projectiles
