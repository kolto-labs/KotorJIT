#include <cassert>
#include <cstdio>
#include <bits/stdc++.h>
#include "/run/media/brunner56/MyBook/Workspaces/KotorPhasor/.worktrees/lua-boundary-validation/src/hooks/registry.hpp"
#define private public
#include "/home/brunner56/kp-live-20260922/pl5-review-scratch/mutant-engine.cpp"
#undef private
int main() {
    kp::hooks::AddressTable table;
    kp::harness::GameAdapter adapter("proof", kp::harness::Layout{}, table, 0);
    assert(adapter.pause_machine_.begin_load() == kp::harness::pause::Status::Ok);
    assert(adapter.pause_machine_.loading());
    adapter.load_step_ = kp::harness::GameAdapter::LoadStep::Armed;
    adapter.load_armed_at_ = std::chrono::steady_clock::now() -
                             kp::harness::GameAdapter::kLoadArmedTimeout;
    adapter.step_load_completion();
    assert(!adapter.pause_machine_.loading());
    // Deliberately mutated acceptance expectation: the real path must go red.
    assert(adapter.end_load_calls_ == 2);
    std::puts("unexpected mutant pass");
}
