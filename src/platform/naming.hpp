// Product naming, and the one place that knows the old name.
//
// The project shipped as KotorPhasor and is now ScriptForge. Installs, scripts
// and launch wrappers made under the old name must keep working, so every
// player-visible name has a current spelling and a legacy spelling, and the
// runtime prefers the current one without ever refusing the legacy one:
//
//   environment   SCRIPTFORGE_<NAME>   then KOTORPHASOR_<NAME>
//   data folder   <game>/scriptforge/  then <game>/kotorphasor/ (whichever exists;
//                                    the current name wins when both do)
//   ini           scriptforge.ini      then kotorphasor.ini
//   runtime DLL   scriptforge.dll      then kphasor.dll  (see src/proxy/binkw32.cpp)
//
// The Lua surface (kp.*, nwscript.*) is not part of the rename: scripts keep
// their names. Serialized format identifiers (receipt schemas and the like)
// keep theirs too, so existing files still validate.
#pragma once

#include <cstdio>
#include <cstdlib>

namespace kp::naming {

inline constexpr const char* kProduct          = "ScriptForge";
inline constexpr const char* kLegacyProduct    = "KotorPhasor";
inline constexpr const char* kDataDir          = "scriptforge";
inline constexpr const char* kLegacyDataDir    = "kotorphasor";
inline constexpr const char* kIniName          = "scriptforge.ini";
inline constexpr const char* kLegacyIniName    = "kotorphasor.ini";
inline constexpr const char* kLogName          = "scriptforge.log";
inline constexpr const char* kProxyLogName     = "scriptforge-proxy.log";
inline constexpr const char* kRuntimeDll       = "scriptforge.dll";
inline constexpr const char* kLegacyRuntimeDll = "kphasor.dll";
inline constexpr const char* kRuntimeSo        = "libscriptforge.so";
inline constexpr const char* kRuntimeDylib     = "libscriptforge.dylib";
inline constexpr const char* kEnvPrefix        = "SCRIPTFORGE_";
inline constexpr const char* kLegacyEnvPrefix  = "KOTORPHASOR_";

// Value of SCRIPTFORGE_<name>, else KOTORPHASOR_<name>, else nullptr. An empty
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
