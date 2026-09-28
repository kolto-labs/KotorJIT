// Independent re-review probes for the x64 Detour fix round (I2, I3, new paths).
// Every scenario runs in a forked child; parent prints PASS/FAIL per scenario.
#include "hooks/x64/trampoline.hpp"

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cerrno>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <functional>
#include <string>
#include <vector>

using namespace kp::hooks::x64;
static const size_t PG = 4096;

static int g_fail = 0;
#define CHECK(c, ...) do { if (!(c)) { ++g_fail; std::fprintf(stderr, "    fail: %s ", #c); std::fprintf(stderr, __VA_ARGS__); std::fprintf(stderr, "\n"); } } while (0)

static std::string perms(const void* p) {
    std::ifstream m("/proc/self/maps");
    std::string l;
    auto a = (uintptr_t)p;
    while (std::getline(m, l)) {
        unsigned long lo, hi; char pr[5] = {};
        if (sscanf(l.c_str(), "%lx-%lx %4s", &lo, &hi, pr) == 3 && a >= lo && a < hi) return pr;
    }
    return "unmapped";
}
// Total bytes of anonymous (no path) mappings: a leaked/unleaked trampoline shows up here.
static unsigned long anon_bytes() {
    std::ifstream m("/proc/self/maps");
    std::string l; unsigned long tot = 0;
    while (std::getline(m, l)) {
        unsigned long lo, hi; char pr[5], off[20], dev[20]; unsigned long ino; int n = 0;
        if (sscanf(l.c_str(), "%lx-%lx %4s %19s %19s %lu %n", &lo, &hi, pr, off, dev, &ino, &n) >= 6 &&
            (n == 0 || l.size() <= (size_t)n || l[n] == 0) && ino == 0 && l.find('[') == std::string::npos)
            tot += hi - lo;
    }
    return tot;
}

// fn(x) = x + 100. 15-byte prologue, no RIP/rel32, then pop/ret.
static const uint8_t FN[] = {0x55, 0x48, 0x89, 0xe5, 0x89, 0xf8, 0x05, 0x64, 0, 0, 0, 0x0f, 0x1f, 0x40, 0x00, 0x5d, 0xc3};

using Fn = int (*)(int);
static Fn volatile g_orig = nullptr;
static int volatile g_det_calls = 0;
extern "C" int det(int x) { ++g_det_calls; return g_orig(x) + 1000; }

static uint8_t* rx_page_with(const uint8_t* b, size_t n, size_t at) {
    auto* p = (uint8_t*)mmap(nullptr, PG, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    memset(p, 0xcc, PG);
    memcpy(p + at, b, n);
    mprotect(p, PG, PROT_READ | PROT_EXEC);
    return p;
}
// Foreign hook: movabs rax, det ; jmp rax  -- written over the target by "someone else".
static void chain_foreign(uint8_t* target) {
    uint8_t stub[12] = {0x48, 0xb8};
    uint64_t d = (uint64_t)&det;
    memcpy(stub + 2, &d, 8); stub[10] = 0xff; stub[11] = 0xe0;
    auto* sp = rx_page_with(stub, 12, 0);
    uint8_t j[12] = {0x48, 0xb8};
    uint64_t s = (uint64_t)sp;
    memcpy(j + 2, &s, 8); j[10] = 0xff; j[11] = 0xe0;
    auto* pg = (uint8_t*)((uintptr_t)target & ~(PG - 1));
    mprotect(pg, PG, PROT_READ | PROT_WRITE);
    memcpy(target, j, 12);
    mprotect(pg, PG, PROT_READ | PROT_EXEC);
}

static int run(const char* name, std::function<void()> body) {
    fflush(stdout);
    pid_t pid = fork();
    if (pid == 0) { g_fail = 0; body(); fflush(stderr); _exit(g_fail ? 1 : 0); }
    int st = 0; waitpid(pid, &st, 0);
    bool ok = WIFEXITED(st) && WEXITSTATUS(st) == 0;
    printf("%s  %s%s\n", ok ? "PASS" : "FAIL", name,
           WIFSIGNALED(st) ? (" (signal " + std::to_string(WTERMSIG(st)) + ")").c_str() : "");
    return ok ? 0 : 1;
}

// Seam used for the two-page partial-failure case: behaves like the kernel
// applying the change VMA by VMA and failing at `g_bad_page`.
static uintptr_t g_bad_page = 0;
static int g_mode = 0;  // 1: refuse PROT_EXEC at bad page (partial), 2: also refuse RW at bad page after first RW
static int g_rw_calls = 0;
static int partial_protect(void* a, size_t len, int prot) {
    auto lo = (uintptr_t)a;
    bool covers = g_bad_page >= lo && g_bad_page < lo + len;
    bool refuse = false;
    if (covers && (prot & PROT_EXEC) && g_mode >= 1) refuse = true;
    if (covers && prot == (PROT_READ | PROT_WRITE)) { ++g_rw_calls; if (g_mode == 2 && g_rw_calls > 1) refuse = true; }
    if (!refuse) return mprotect(a, len, prot);
    if (g_bad_page > lo) mprotect(a, g_bad_page - lo, prot);  // pages before the bad one change
    errno = EACCES;
    return -1;
}

int main() {
    int bad = 0;
    printf("pagesize=%ld\n", sysconf(_SC_PAGESIZE));

    // ---- I2 ----------------------------------------------------------------
    bad += run("I2 dtor after foreign chain: trampoline kept, chained call works, leak counted", [] {
        auto* code = rx_page_with(FN, sizeof FN, 128);
        Fn f = (Fn)(code + 128);
        CHECK(f(5) == 105, "pre");
        auto leaks0 = leaked_trampoline_pages();
        void* tramp;
        {
            Detour d;
            CHECK(d.install(code + 128, (void*)&det) == HookStatus::Ok, "install");
            g_orig = (Fn)(tramp = d.original());
            CHECK(f(5) == 1105, "hooked");
            chain_foreign(code + 128);
            CHECK(d.uninstall() == HookStatus::PatchClobbered && d.installed(), "uninstall refuses");
        }
        CHECK(leaked_trampoline_pages() == leaks0 + 1, "leak count %zu", leaked_trampoline_pages());
        CHECK(perms(tramp) == "r-xp", "tramp %s", perms(tramp).c_str());
        CHECK(f(5) == 1105, "chained call after destroy");
    });
    bad += run("I2 move-assign after chain; reused Detour installs+uninstalls cleanly, no extra leak", [] {
        auto* code = rx_page_with(FN, sizeof FN, 128);
        auto* code2 = rx_page_with(FN, sizeof FN, 256);
        Fn f = (Fn)(code + 128), f2 = (Fn)(code2 + 256);
        Detour d;
        CHECK(d.install(code + 128, (void*)&det) == HookStatus::Ok, "install");
        void* tramp = d.original();
        g_orig = (Fn)tramp;
        chain_foreign(code + 128);
        d = Detour();
        CHECK(!d.installed() && d.original() == nullptr && d.trampoline_page() == nullptr, "moved-into empty");
        CHECK(leaked_trampoline_pages() == 1, "leak=%zu", leaked_trampoline_pages());
        CHECK(perms(tramp) == "r-xp" && f(5) == 1105, "chain works");
        CHECK(d.install(code2 + 256, (void*)&det) == HookStatus::Ok, "reuse install");
        Fn saved = g_orig; g_orig = (Fn)d.original();
        CHECK(f2(5) == 1105, "reuse hooked");
        CHECK(d.uninstall() == HookStatus::Ok && f2(5) == 105, "reuse uninstall");
        g_orig = saved;
        CHECK(leaked_trampoline_pages() == 1, "leak unchanged %zu", leaked_trampoline_pages());
    });
    bad += run("I2 move-construct from installed: source inert, one uninstall, no leak", [] {
        auto* code = rx_page_with(FN, sizeof FN, 128);
        Fn f = (Fn)(code + 128);
        {
            Detour a;
            CHECK(a.install(code + 128, (void*)&det) == HookStatus::Ok, "install");
            g_orig = (Fn)a.original();
            Detour b(std::move(a));
            CHECK(!a.installed() && b.installed(), "moved");
            CHECK(f(5) == 1105, "hooked via b");
        }
        CHECK(f(5) == 105 && leaked_trampoline_pages() == 0, "restored, leak=%zu", leaked_trampoline_pages());
        CHECK(memcmp(code + 128, FN, sizeof FN) == 0, "bytes");
    });

    // ---- I3 with a REAL kernel refusal (no seam) ----------------------------
    bad += run("real kernel: RW refused on MAP_SHARED O_RDONLY r-x file mapping -> nothing written, no page left behind", [] {
        char path[] = "/home/brunner56/kp-live-20260922/review-probes-m0m1-r2/codeXXXXXX";
        int fd = mkstemp(path);
        std::vector<uint8_t> buf(PG, 0xcc); memcpy(buf.data() + 128, FN, sizeof FN);
        CHECK(write(fd, buf.data(), PG) == (ssize_t)PG, "write"); close(fd);
        fd = open(path, O_RDONLY); unlink(path);
        auto* code = (uint8_t*)mmap(nullptr, PG, PROT_READ | PROT_EXEC, MAP_SHARED, fd, 0);
        CHECK(code != MAP_FAILED, "mmap");
        Fn f = (Fn)(code + 128);
        CHECK(f(5) == 105, "pre");
        auto anon0 = anon_bytes();
        Detour d; const char* det_s = nullptr;
        auto st = d.install(code + 128, (void*)&det, nullptr, 0, &det_s);
        fprintf(stderr, "    status=%s detail=%s errno-path\n", to_string(st), det_s ? det_s : "");
        CHECK(st == HookStatus::ProtectFailed && !d.installed(), "refused");
        CHECK(memcmp(code + 128, FN, sizeof FN) == 0, "bytes untouched");
        CHECK(perms(code) == "r-xs", "perms %s", perms(code).c_str());
        CHECK(anon_bytes() == anon0, "trampoline unmapped (anon %lu -> %lu)", anon0, anon_bytes());
        CHECK(f(5) == 105 && leaked_trampoline_pages() == 0, "callable");
    });
    bad += run("real kernel PARTIAL mprotect over two VMAs (anon r-x | shared-RO file r-x): page0 resealed, nothing written", [] {
        // Reserve two pages, then put a private anon page and a shared read-only file page side by side.
        auto* base = (uint8_t*)mmap(nullptr, 2 * PG, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        char path[] = "/home/brunner56/kp-live-20260922/review-probes-m0m1-r2/codeXXXXXX";
        int fd = mkstemp(path);
        const size_t at = PG - 6;  // prologue crosses the page boundary after 6 bytes
        std::vector<uint8_t> file(PG, 0xcc); memcpy(file.data(), FN + 6, sizeof FN - 6);
        CHECK(write(fd, file.data(), PG) == (ssize_t)PG, "write"); close(fd);
        fd = open(path, O_RDONLY); unlink(path);
        auto* p0 = (uint8_t*)mmap(base, PG, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED, -1, 0);
        memset(p0, 0xcc, PG); memcpy(p0 + at, FN, 6);
        mprotect(p0, PG, PROT_READ | PROT_EXEC);
        auto* p1 = (uint8_t*)mmap(base + PG, PG, PROT_READ | PROT_EXEC, MAP_SHARED | MAP_FIXED, fd, 0);
        CHECK(p0 == base && p1 == base + PG, "layout");
        Fn f = (Fn)(base + at);
        CHECK(f(5) == 105, "pre");
        // Show the kernel really is partial here.
        errno = 0;
        int r = mprotect(base, 2 * PG, PROT_READ | PROT_WRITE);
        fprintf(stderr, "    raw mprotect(2 pages, RW) = %d errno=%d page0=%s page1=%s\n", r, errno,
                perms(base).c_str(), perms(base + PG).c_str());
        mprotect(base, PG, PROT_READ | PROT_EXEC);
        auto anon0 = anon_bytes();
        Detour d; const char* ds = nullptr;
        auto st = d.install(base + at, (void*)&det, nullptr, 0, &ds);
        fprintf(stderr, "    status=%s detail=%s page0=%s page1=%s\n", to_string(st), ds ? ds : "",
                perms(base).c_str(), perms(base + PG).c_str());
        CHECK(st == HookStatus::ProtectFailed && !d.installed(), "refused");
        CHECK(perms(base) == "r-xp", "page0 resealed: %s", perms(base).c_str());
        CHECK(memcmp(base + at, FN, 6) == 0 && memcmp(base + PG, FN + 6, sizeof FN - 6) == 0, "bytes");
        CHECK(anon_bytes() == anon0, "no trampoline left");
        CHECK(f(5) == 105, "callable");
    });

    // ---- I3 two-page span via seam (kernel-like partial behaviour) ----------
    bad += run("seam two-page: restore refused on page1 only -> rolled back; page0 r-x, page1 rw, not installed", [] {
        auto* base = (uint8_t*)mmap(nullptr, 2 * PG, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        memset(base, 0xcc, 2 * PG);
        const size_t at = PG - 6;
        memcpy(base + at, FN, sizeof FN);
        mprotect(base, 2 * PG, PROT_READ | PROT_EXEC);
        g_bad_page = (uintptr_t)base + PG; g_mode = 1; g_rw_calls = 0;
        testing::set_protect_hook(partial_protect);
        Detour d; const char* ds = nullptr;
        auto st = d.install(base + at, (void*)&det, nullptr, 0, &ds);
        testing::set_protect_hook(nullptr);
        fprintf(stderr, "    status=%s detail=%s page0=%s page1=%s\n", to_string(st), ds ? ds : "",
                perms(base).c_str(), perms(base + PG).c_str());
        CHECK(st == HookStatus::ProtectFailed && !d.installed(), "refused");
        CHECK(memcmp(base + at, FN, sizeof FN) == 0, "rolled back");
        CHECK(perms(base) == "r-xp", "page0 %s", perms(base).c_str());
        CHECK(perms(base + PG) == "rw-p", "page1 %s (documented dead page)", perms(base + PG).c_str());
        CHECK(ds && strstr(ds, "left RW"), "detail names RW");
    });
    bad += run("seam two-page: restore AND second RW refused on page1 -> patch live, installed; page0 state?", [] {
        auto* base = (uint8_t*)mmap(nullptr, 2 * PG, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        memset(base, 0xcc, 2 * PG);
        const size_t at = PG - 6;
        memcpy(base + at, FN, sizeof FN);
        mprotect(base, 2 * PG, PROT_READ | PROT_EXEC);
        g_bad_page = (uintptr_t)base + PG; g_mode = 2; g_rw_calls = 0;
        testing::set_protect_hook(partial_protect);
        Detour d; const char* ds = nullptr;
        auto st = d.install(base + at, (void*)&det, nullptr, 0, &ds);
        testing::set_protect_hook(nullptr);
        fprintf(stderr, "    status=%s installed=%d detail=%s page0=%s page1=%s\n", to_string(st), d.installed(),
                ds ? ds : "", perms(base).c_str(), perms(base + PG).c_str());
        CHECK(st == HookStatus::ProtectFailed && d.installed(), "installed with ProtectFailed");
        CHECK(base[at] == 0xff && base[at + 1] == 0x25, "patch live");
        g_orig = (Fn)d.original();
        CHECK(d.uninstall() == HookStatus::Ok, "uninstall recovers");
        CHECK(memcmp(base + at, FN, sizeof FN) == 0 && perms(base) == "r-xp" && perms(base + PG) == "r-xp",
              "restored %s %s", perms(base).c_str(), perms(base + PG).c_str());
        CHECK(((Fn)(base + at))(5) == 105, "callable");
    });
    bad += run("seam: exec ALWAYS refused on install (g_mode=1 refuses every PROT_EXEC on the page) -> page left rw-; retry install on the dead page", [] {
        auto* code = rx_page_with(FN, sizeof FN, 128);
        g_bad_page = (uintptr_t)code; g_mode = 1; g_rw_calls = 0;
        testing::set_protect_hook(partial_protect);
        Detour d;
        auto st = d.install(code + 128, (void*)&det);
        testing::set_protect_hook(nullptr);
        CHECK(st == HookStatus::ProtectFailed && !d.installed(), "refused");
        CHECK(perms(code) == "rw-p", "page %s", perms(code).c_str());
        // Documented dead page; a retry records rw- as the protection and would keep it non-exec.
        auto st2 = d.install(code + 128, (void*)&det);
        fprintf(stderr, "    retry on the dead page: %s, page=%s\n", to_string(st2), perms(code).c_str());
    });

    printf("%s (%d failing)\n", bad ? "PROBES FAILED" : "ALL PROBES PASS", bad);
    return bad ? 1 : 0;
}
