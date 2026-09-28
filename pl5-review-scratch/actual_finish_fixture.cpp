// Private linkage proof: include the production scratch TU so this calls the
// real GameAdapter constructor and finish_load implementation, not a copy.
#include <cassert>
#include <cstdio>
#include <bits/stdc++.h>

#include "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/hooks/registry.hpp"
#define private public
#include "/home/brunner56/kp-live-20260922/pl5-scratch/src/harness/engine_k1.cpp"
#undef private

int main() {
    kp::hooks::AddressTable table;
    kp::harness::Layout layout;
    kp::harness::GameAdapter adapter("proof", layout, table, 0);
    assert(!adapter.pause_machine_.loading());
    assert(adapter.pause_machine_.begin_load() == kp::harness::pause::Status::Ok);
    assert(adapter.pause_machine_.loading());
    adapter.load_step_ = kp::harness::GameAdapter::LoadStep::Armed;
    adapter.load_armed_at_ = std::chrono::steady_clock::now() -
                             kp::harness::GameAdapter::kLoadArmedTimeout;
    adapter.step_load_completion();
    assert(adapter.load_step_ == kp::harness::GameAdapter::LoadStep::GaveUp);
    assert(!adapter.pause_machine_.loading());
    assert(adapter.end_load_calls_ == 1);
    std::puts("actual GameAdapter::step_load_completion -> finish_load call path: PASS");
}
