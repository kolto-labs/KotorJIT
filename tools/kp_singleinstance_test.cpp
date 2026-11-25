// One ScriptForge runtime per process, however many copies get loaded.
//
// The runtime can arrive by several routes -- the binkw32 proxy, the launcher's
// injection, KPM's DLL-only patch, DT_NEEDED or LD_PRELOAD -- and two of them
// can be set up at once with different files (a game-folder scriptforge.dll and
// KPM's extracted windows_x86.dll; a preloaded libscriptforge.so and a
// DT_NEEDED copy). Each copy that starts its own runtime would hook every site
// a second time. This test loads two copies of the real library into one
// process and counts how many runtimes announce themselves in the log.
//
// The parent copies this executable and the library into a fresh directory and
// runs that copy as the "game", so the runtime's game_dir -- and so its log --
// is private to the test.
#include <dlfcn.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>

#ifndef KP_RUNTIME_SO
#error "KP_RUNTIME_SO must name the built libscriptforge.so"
#endif

namespace {

int g_failures = 0;
void check(bool ok, const char* what) {
    std::printf("%s %s\n", ok ? "ok  " : "FAIL", what);
    if (!ok) ++g_failures;
}

bool copy_file(const std::string& from, const std::string& to, mode_t mode) {
    std::ifstream in(from, std::ios::binary);
    std::ofstream out(to, std::ios::binary);
    if (!in || !out) return false;
    out << in.rdbuf();
    out.close();
    return chmod(to.c_str(), mode) == 0;
}

std::string self_path() {
    char buf[4096] = {0};
    const ssize_t n = readlink("/proc/self/exe", buf, sizeof buf - 1);
    return n > 0 ? std::string(buf, static_cast<std::size_t>(n)) : std::string();
}

int count_banners(const std::string& log) {
    std::ifstream f(log);
    std::string line;
    int n = 0;
    while (std::getline(f, line))
        if (line.find("ScriptForge ") != std::string::npos && line.find(" starting (") != std::string::npos) ++n;
    return n;
}

// Child: the "game". Load both copies, give their workers time to log, exit.
int child(const char* a, const char* b) {
    for (const char* lib : {a, b}) {
        if (dlopen(lib, RTLD_NOW | RTLD_LOCAL) == nullptr) {
            std::fprintf(stderr, "dlopen %s: %s\n", lib, dlerror());
            return 2;
        }
    }
    sleep(3);
    _exit(0);   // skip static destructors of two half-started runtimes
}

// Runs one scenario in a fresh directory; returns how many runtimes started.
int run_scenario(const char* inherited_claim) {
    char tmpl[] = "/tmp/kp_singleinstance.XXXXXX";
    const char* dir = mkdtemp(tmpl);
    if (dir == nullptr) return -1;
    const std::string d = dir;
    const std::string game = d + "/game", a = d + "/copy_a.so", b = d + "/copy_b.so";
    if (!copy_file(self_path(), game, 0755) || !copy_file(KP_RUNTIME_SO, a, 0755) ||
        !copy_file(KP_RUNTIME_SO, b, 0755))
        return -1;

    const pid_t pid = fork();
    if (pid == 0) {
        unsetenv("SCRIPTFORGE_NO_AUTOSTART");
        unsetenv("KOTORPHASOR_NO_AUTOSTART");
        if (inherited_claim != nullptr) setenv("SCRIPTFORGE_RUNTIME_PID", inherited_claim, 1);
        else unsetenv("SCRIPTFORGE_RUNTIME_PID");
        execl(game.c_str(), game.c_str(), "child", a.c_str(), b.c_str(), static_cast<char*>(nullptr));
        _exit(127);
    }
    int status = 0;
    waitpid(pid, &status, 0);
    const int banners = count_banners(d + "/scriptforge.log");
    if (std::system(("rm -rf '" + d + "'").c_str()) != 0) std::fprintf(stderr, "could not remove %s\n", d.c_str());
    return (WIFEXITED(status) && WEXITSTATUS(status) == 0) ? banners : -100 - WEXITSTATUS(status);
}

}  // namespace

int main(int argc, char** argv) {
    if (argc == 4 && std::strcmp(argv[1], "child") == 0) return child(argv[2], argv[3]);

    const int two_copies = run_scenario(nullptr);
    std::printf("     two copies -> %d runtime(s) started\n", two_copies);
    check(two_copies == 1, "two copies of the runtime in one process start exactly one runtime");

    // A claim left in the environment by a parent process (another pid) is
    // not a claim on this process.
    const int inherited = run_scenario("1");
    std::printf("     inherited foreign claim -> %d runtime(s) started\n", inherited);
    check(inherited == 1, "a claim inherited from another process does not suppress this one");

    if (g_failures) std::printf("%d failure(s)\n", g_failures);
    else std::printf("all single-instance checks passed\n");
    return g_failures ? 1 : 0;
}
