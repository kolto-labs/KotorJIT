// Product naming, and the one place that knows the old name.
//
// The project shipped as KotorPhasor and is now Hyperstim. Installs, scripts
// and launch wrappers made under the old name must keep working, so every
// player-visible name has a current spelling and a legacy spelling, and the
// runtime prefers the current one without ever refusing the legacy one:
//
//   environment   HYPERSTIM_<NAME>   then KOTORPHASOR_<NAME>
//   data folder   <game>/hyperstim/  then <game>/kotorphasor/ (whichever exists;
//                                    the current name wins when both do)
//   ini           hyperstim.ini      then kotorphasor.ini
//   runtime DLL   hyperstim.dll      then kphasor.dll  (see src/proxy/binkw32.cpp)
//
// The Lua surface (kp.*, nwscript.*) is not part of the rename: scripts keep
// their names. Serialized format identifiers (receipt schemas and the like)
// keep theirs too, so existing files still validate.
#pragma once

#include <cstdio>
#include <cstdlib>

namespace kp::naming {

inline constexpr const char* kProduct          = "Hyperstim";
inline constexpr const char* kLegacyProduct    = "KotorPhasor";
inline constexpr const char* kDataDir          = "hyperstim";
inline constexpr const char* kLegacyDataDir    = "kotorphasor";
inline constexpr const char* kIniName          = "hyperstim.ini";
inline constexpr const char* kLegacyIniName    = "kotorphasor.ini";
inline constexpr const char* kLogName          = "hyperstim.log";
inline constexpr const char* kEnvPrefix        = "HYPERSTIM_";
inline constexpr const char* kLegacyEnvPrefix  = "KOTORPHASOR_";

// Value of HYPERSTIM_<name>, else KOTORPHASOR_<name>, else nullptr. An empty
// value counts as unset, matching how every caller already treated getenv.
// The returned pointer is getenv's, so it stays valid until the environment
// is modified -- the same lifetime callers relied on before.
inline const char* env(const char* name) {
    char key[128];
    for (const char* prefix : {kEnvPrefix, kLegacyEnvPrefix}) {
        const int n = std::snprintf(key, sizeof key, "%s%s", prefix, name);
        if (n <= 0 || static_cast<std::size_t>(n) >= sizeof key) continue;
        const char* v = std::getenv(key);
        if (v != nullptr && *v != '\0') return v;
    }
    return nullptr;
}

}  // namespace kp::naming
