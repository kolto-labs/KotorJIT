#include "hooks/x64/trampoline.hpp"
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include <cstdio>
#include <cstring>
#include <cstdint>
#include <functional>
using namespace kp::hooks::x64;
static long PS; static int fails = 0;
static int det(int x) { return x + 1000; }
static void child(const char* name, std::function<int()> fn) {
    pid_t p = fork();
    if (p == 0) _exit(fn());
    int st; waitpid(p, &st, 0);
    bool ok = WIFEXITED(st) && WEXITSTATUS(st) == 0;
    if (!ok) ++fails;
    std::printf("%s  %s%s\n", ok ? "PASS" : "FAIL", name,
                WIFSIGNALED(st) ? " (killed by signal)" : (ok ? "" : " (exit != 0)"));
}
// two pages: page0 prot0, page1 prot1
static uint8_t* two(int p0, int p1) {
    auto* m = (uint8_t*)mmap(nullptr, 2*PS, PROT_READ|PROT_WRITE, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);
    memset(m, 0xcc, 2*PS);
    return m;
}
static void seal(uint8_t* m, int p0, int p1) { mprotect(m, PS, p0); mprotect(m+PS, PS, p1); }
static void snap(uint8_t* at, uint8_t* out, size_t n) { memcpy(out, at, n); }
// 16 bytes of real code: mov eax,edi (89 f8) ; add eax,100 (05 64 00 00 00) ; nop7 (0f 1f 80 00 00 00 00); ret... needs >=14 before ret
static const uint8_t fn16[] = {0x89,0xf8, 0x05,0x64,0,0,0, 0x0f,0x1f,0x80,0,0,0,0, 0x66,0x90, 0xc3};
int main() {
    PS = sysconf(_SC_PAGESIZE);
    setvbuf(stdout, nullptr, _IONBF, 0);
    child("PROT_NONE target -> Unreadable, no fault", [] {
        auto* m = two(0,0); seal(m, PROT_NONE, PROT_NONE);
        Detour d; const char* dt; auto s = d.install(m, (void*)det, nullptr, 0, &dt);
        std::printf("    status=%s detail=%s\n", to_string(s), dt ? dt : "-");
        return s == HookStatus::Unreadable && !d.installed() ? 0 : 1; });
    child("PROT_NONE target with expect -> Unreadable, no fault", [] {
        auto* m = two(0,0); seal(m, PROT_NONE, PROT_NONE);
        Detour d; auto s = d.install(m, (void*)det, fn16, 4);
        return s == HookStatus::Unreadable ? 0 : 1; });
    child("unmapped target -> Unreadable, no fault", [] {
        auto* m = two(0,0); munmap(m, 2*PS);
        Detour d; const char* dt; auto s = d.install(m + 5, (void*)det, nullptr, 0, &dt);
        std::printf("    status=%s detail=%s\n", to_string(s), dt ? dt : "-");
        return s == HookStatus::Unreadable ? 0 : 1; });
    child("window crosses r-x | --- (8 bytes left) -> Unreadable, bytes+prot unchanged", [] {
        auto* m = two(0,0); uint8_t* at = m + PS - 8; memcpy(at, fn16, 8); seal(m, PROT_READ|PROT_EXEC, PROT_NONE);
        uint8_t before[8]; snap(at, before, 8);
        Detour d; const char* dt; auto s = d.install(at, (void*)det, nullptr, 0, &dt);
        std::printf("    status=%s detail=%s\n", to_string(s), dt ? dt : "-");
        return s == HookStatus::Unreadable && !memcmp(before, at, 8) && d.trampoline_page() == nullptr ? 0 : 1; });
    child("window crosses r-x | unmapped -> Unreadable", [] {
        auto* m = two(0,0); uint8_t* at = m + PS - 8; memcpy(at, fn16, 8); seal(m, PROT_READ|PROT_EXEC, PROT_NONE);
        munmap(m + PS, PS);
        Detour d; auto s = d.install(at, (void*)det);
        std::printf("    status=%s\n", to_string(s));
        return s == HookStatus::Unreadable ? 0 : 1; });
    child("expect_len beyond window -> Unreadable, no read past window", [] {
        auto* m = two(0,0); uint8_t* at = m + PS - 8; memcpy(at, fn16, 8); seal(m, PROT_READ|PROT_EXEC, PROT_NONE);
        Detour d; auto s = d.install(at, (void*)det, fn16, 12);
        return s == HookStatus::Unreadable ? 0 : 1; });
    child("guard page: 17 stolen-able bytes end before --- -> installs, calls, uninstalls", [] {
        auto* m = two(0,0); uint8_t* at = m + PS - sizeof fn16; memcpy(at, fn16, sizeof fn16);
        seal(m, PROT_READ|PROT_EXEC, PROT_NONE);
        auto f = (int(*)(int))at; if (f(5) != 105) return 2;
        Detour d; const char* dt; auto s = d.install(at, (void*)det, nullptr, 0, &dt);
        std::printf("    status=%s stolen=%zu detail=%s\n", to_string(s), d.stolen_bytes(), dt ? dt : "-");
        if (s != HookStatus::Ok) return 3;
        if (f(5) != 1005) return 4;
        if (((int(*)(int))d.original())(5) != 105) return 5;
        if (d.uninstall() != HookStatus::Ok) return 6;
        if (memcmp(at, fn16, sizeof fn16) || f(5) != 105) return 7;
        return 0; });
    child("exact edge: 14 stolen bytes end exactly at --- page -> Ok, uninstall restores", [] {
        auto* m = two(0,0); uint8_t* at = m + PS - 14; memcpy(at, fn16, 14);
        seal(m, PROT_READ|PROT_EXEC, PROT_NONE);
        Detour d; const char* dt; auto s = d.install(at, (void*)det, nullptr, 0, &dt);
        std::printf("    status=%s stolen=%zu detail=%s\n", to_string(s), d.stolen_bytes(), dt ? dt : "-");
        if (s != HookStatus::Ok || d.stolen_bytes() != 14) return 3;
        if (d.uninstall() != HookStatus::Ok || memcmp(at, fn16, 14)) return 4;
        return 0; });
    child("exact edge minus one: 13 r-x bytes then --- -> Unreadable", [] {
        auto* m = two(0,0); uint8_t* at = m + PS - 13; memcpy(at, fn16, 13);
        seal(m, PROT_READ|PROT_EXEC, PROT_NONE);
        Detour d; auto s = d.install(at, (void*)det);
        std::printf("    status=%s\n", to_string(s));
        return s == HookStatus::Unreadable ? 0 : 1; });
    // mislabel probe: overlong (17-byte) instruction, 20 readable bytes before a --- page
    static const uint8_t overlong[] = {0x66,0x66,0x66,0x66,0x66,0x66,0x66,0x66,0x66,0x66, 0x8b,0x84,0x00, 0,0,0,0, 0x90,0x90,0x90};
    child("INFO overlong insn, fully mapped page: status", [] {
        auto* m = two(0,0); uint8_t* at = m + 64; memcpy(at, overlong, sizeof overlong); seal(m, PROT_READ|PROT_EXEC, PROT_READ|PROT_EXEC);
        Detour d; const char* dt; auto s = d.install(at, (void*)det, nullptr, 0, &dt);
        std::printf("    status=%s detail=%s\n", to_string(s), dt ? dt : "-");
        return 0; });
    child("INFO overlong insn, 20 bytes before --- page: status", [] {
        auto* m = two(0,0); uint8_t* at = m + PS - sizeof overlong; memcpy(at, overlong, sizeof overlong); seal(m, PROT_READ|PROT_EXEC, PROT_NONE);
        Detour d; const char* dt; auto s = d.install(at, (void*)det, nullptr, 0, &dt);
        std::printf("    status=%s detail=%s\n", to_string(s), dt ? dt : "-");
        return s == HookStatus::DecodeFailed ? 0 : 1; });
    std::printf(fails ? "%d FAILING\n" : "ALL PASS\n", fails);
    return fails != 0;
}
