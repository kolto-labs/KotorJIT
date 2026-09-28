#include <cstdarg>
#include <string>
#include <string_view>
#include "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/platform/platform.hpp"
#include "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/lua/host.hpp"
#include "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/runtime/runtime.hpp"
#include "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/runtime/internal.hpp"
#include "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/hooks/registry.hpp"
#include "/home/brunner56/kp-live-20260922/pl5-scratch/src/harness/fields.hpp"

namespace kp::platform {
bool is_readable(const void*, std::size_t) { return true; }
bool set_protection(void*, std::size_t, Protect) { return true; }
void log(LogLevel, const char*, ...) {}
}

namespace kp::runtime {
Runtime& Runtime::instance() { static Runtime r; return r; }
void enter_hook_body() {}
void leave_hook_body() {}
multiplayer::Transport* active_multiplayer_transport() { return nullptr; }
std::string self_module_path() { return "."; }
std::string directory_of(const std::string& p) { return p; }
}

namespace kp::hooks {
void* HookSet::original(std::string_view) const { return nullptr; }
}

namespace kp::harness {
std::unique_ptr<EngineAdapter> make_k2_adapter(const hooks::AddressTable&, std::uintptr_t) {
    return nullptr;
}
}

// Scratch-only lifetime stubs: Runtime::instance() is never started in this
// fixture, so these production-owned members are guaranteed null.
kp::multiplayer::Transport::~Transport() {}
kp::lua::Host::~Host() {}
kp::hooks::HookSet::~HookSet() {}
kp::lua::Script::~Script() {}
kp::hooks::Detour::~Detour() {}
