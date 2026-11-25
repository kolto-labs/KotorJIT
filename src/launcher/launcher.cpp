// Win32 runtime-injection launcher for KotorJIT (KPM-style ProcessInjector).
//
// Deployment modes:
//   direct -- CreateProcessA(CREATE_SUSPENDED) -> remote LoadLibraryA -> ResumeThread.
//             Injects before CRT/main/game initialization runs (GOG, unpacked, K2 Aspyr).
//   steam  -- ShellExecuteA launch (for SteamStub DRM) -> poll until real game process
//             stabilizes (0x400000 'MZ' readable, survives 500 ms bootstrap filter,
//             visible main window) -> remote LoadLibraryA.
//   attach -- Attach to an already-running process by --pid or exe name -> LoadLibraryA.
//   auto   -- Picks 'steam' when swkotor.exe matches packed K1 Steam or carries a .bind
//             PE section; otherwise picks 'direct'.
//
// Under Wine/Proton or when immediate pre-SteamStub entry hooking on packed Steam K1
// is needed, the optional binkw32.dll proxy remains supported.

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <shellapi.h>

#include <algorithm>
#include <cerrno>
#include <cctype>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <string>
#include <vector>

#include "image/sha256.hpp"
#include "platform/naming.hpp"

namespace {

constexpr char kVersion[] = "0.1.0";

// Known Windows game SHA-256 digests matching src/generated/builds.inc.
struct KnownBuild {
    const char* sha256;
    const char* alias;
    bool steam_packed;
    const char* steam_app_id;
};

constexpr KnownBuild kKnownBuilds[] = {
    {"9c10e0450a6eeca417e036e3cde7474fed1f0a92aab018446d156944dea91435", "k1_gog_103", false, ""},
    {"34e6d971c034222a417995d8e1e8fdd9f8781795c9c289bd86c499a439f34c88", "k1_steam_103", true, "32370"},
    {"2719ed2cb678e2c1ff5b2a787f9804d8e5f8dd52a02c2279080f031636e03a05", "k1_steam_103_unpacked", false, ""},
    {"777bee235a9e8bdd9863f6741bc3ac54bb6a113b62b1d2e4d12bbe6db963a914", "k2_gog_aspyr", false, ""},
    {"6a522e71631dcee93467bd2010f3b23d9145326e1e2e89305f13ab104dbbffef", "k2_steam_aspyr", false, "208580"},
};

enum class Mode {
    Auto,
    Direct,
    Steam,
    Attach,
};

struct Options {
    Mode mode = Mode::Auto;
    std::string exe_path;
    std::string dll_path;
    DWORD pid = 0;
    DWORD timeout_ms = 60000;
    bool wait = false;
    bool wait_window = true;
    bool check_only = false;
    std::vector<std::string> game_args;
};

struct PeInspection {
    bool valid_pe = false;
    bool is_i386 = false;
    bool is_pe32 = false;
    bool has_bind_section = false;
    std::uint16_t machine = 0;
};

bool parse_uint_dec(const char* s, unsigned long& out) {
    if (s == nullptr || *s == '\0') return false;
    for (const char* p = s; *p != '\0'; ++p) {
        if (!std::isdigit(static_cast<unsigned char>(*p))) return false;
    }
    errno = 0;
    char* end = nullptr;
    const unsigned long v = std::strtoul(s, &end, 10);
    if (errno == ERANGE || end == s || *end != '\0') return false;
    out = v;
    return true;
}

std::string to_lower_ascii(std::string s) {
    for (char& c : s) {
        c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
    }
    return s;
}

std::string basename_of(const std::string& path) {
    const std::size_t pos = path.find_last_of("\\/");
    return pos == std::string::npos ? path : path.substr(pos + 1);
}

std::string dirname_of(const std::string& path) {
    const std::size_t pos = path.find_last_of("\\/");
    return pos == std::string::npos ? "." : path.substr(0, pos);
}

std::string join_win(const std::string& dir, const std::string& leaf) {
    if (dir.empty() || dir == ".") return leaf;
    if (dir.back() == '\\' || dir.back() == '/') return dir + leaf;
    return dir + "\\" + leaf;
}

std::wstring utf8_to_wide(const std::string& s) {
    if (s.empty()) return {};
    int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s.data(),
                                static_cast<int>(s.size()), nullptr, 0);
    UINT cp = CP_UTF8;
    DWORD flags = MB_ERR_INVALID_CHARS;
    if (n <= 0) {
        cp = CP_ACP;
        flags = 0;
        n = MultiByteToWideChar(cp, flags, s.data(), static_cast<int>(s.size()), nullptr, 0);
    }
    if (n <= 0) return {};
    std::wstring w(static_cast<std::size_t>(n), L'\0');
    MultiByteToWideChar(cp, flags, s.data(), static_cast<int>(s.size()), w.data(), n);
    return w;
}

std::string wide_to_utf8(const wchar_t* s, int len = -1) {
    if (s == nullptr) return {};
    if (len == 0 || (len < 0 && s[0] == L'\0')) return {};
    const int n = WideCharToMultiByte(CP_UTF8, 0, s, len, nullptr, 0, nullptr, nullptr);
    if (n <= 0) return {};
    std::string out(static_cast<std::size_t>(n), '\0');
    WideCharToMultiByte(CP_UTF8, 0, s, len, out.data(), n, nullptr, nullptr);
    if (len < 0 && !out.empty() && out.back() == '\0') out.pop_back();
    return out;
}

std::uint64_t tick_now_ms() {
    using Tick64Fn = ULONGLONG(WINAPI*)();
    HMODULE k32 = GetModuleHandleA("kernel32.dll");
    if (k32 != nullptr) {
        auto fn = reinterpret_cast<Tick64Fn>(
            reinterpret_cast<void*>(GetProcAddress(k32, "GetTickCount64")));
        if (fn != nullptr) return static_cast<std::uint64_t>(fn());
    }
    return static_cast<std::uint64_t>(GetTickCount());
}

bool file_exists(const std::string& path) {
    const std::wstring w = utf8_to_wide(path);
    const DWORD attr = w.empty() ? INVALID_FILE_ATTRIBUTES : GetFileAttributesW(w.c_str());
    return attr != INVALID_FILE_ATTRIBUTES && (attr & FILE_ATTRIBUTE_DIRECTORY) == 0;
}

std::string abs_path_of(const std::string& path) {
    const std::wstring w = utf8_to_wide(path);
    if (w.empty()) return path;
    std::wstring buf(1024, L'\0');
    DWORD n = GetFullPathNameW(w.c_str(), static_cast<DWORD>(buf.size()), buf.data(), nullptr);
    if (n >= buf.size()) {
        buf.resize(n + 1);
        n = GetFullPathNameW(w.c_str(), static_cast<DWORD>(buf.size()), buf.data(), nullptr);
    }
    if (n == 0 || n >= buf.size()) return path;
    return wide_to_utf8(buf.data(), static_cast<int>(n));
}

std::string self_dir() {
    std::wstring buf(1024, L'\0');
    for (;;) {
        const DWORD n = GetModuleFileNameW(nullptr, buf.data(), static_cast<DWORD>(buf.size()));
        if (n == 0) return ".";
        if (n < buf.size()) return dirname_of(wide_to_utf8(buf.data(), static_cast<int>(n)));
        if (buf.size() >= 32768) return ".";
        buf.resize(buf.size() * 2);
    }
}

bool running_under_wine() {
    HMODULE ntdll = GetModuleHandleA("ntdll.dll");
    return ntdll != nullptr && GetProcAddress(ntdll, "wine_get_version") != nullptr;
}

bool looks_like_kotorjit_proxy(const std::string& bink_path) {
    const std::wstring w = utf8_to_wide(bink_path);
    if (w.empty()) return false;
    std::FILE* f = _wfopen(w.c_str(), L"rb");
    if (f == nullptr) return false;
    std::string data;
    char chunk[8192];
    for (;;) {
        const std::size_t n = std::fread(chunk, 1, sizeof(chunk), f);
        if (n > 0) data.append(chunk, n);
        if (data.size() >= 200000) {
            std::fclose(f);
            return false;
        }
        if (n < sizeof(chunk)) break;
    }
    std::fclose(f);
    if (data.empty()) return false;
    return data.find(kp::naming::kRuntimeDll) != std::string::npos ||
           data.find(kp::naming::kLegacyRuntimeDll) != std::string::npos;
}

PeInspection inspect_pe(const std::string& path) {
    PeInspection out;
    const std::wstring w = utf8_to_wide(path);
    std::FILE* f = !w.empty() ? _wfopen(w.c_str(), L"rb") : std::fopen(path.c_str(), "rb");
    if (f == nullptr) return out;

    std::uint8_t dos[64]{};
    if (std::fread(dos, 1, sizeof(dos), f) != sizeof(dos)) { std::fclose(f); return out; }
    if (dos[0] != 'M' || dos[1] != 'Z') { std::fclose(f); return out; }

    const std::uint32_t e_lfanew = static_cast<std::uint32_t>(dos[0x3c]) |
                                   (static_cast<std::uint32_t>(dos[0x3d]) << 8) |
                                   (static_cast<std::uint32_t>(dos[0x3e]) << 16) |
                                   (static_cast<std::uint32_t>(dos[0x3f]) << 24);
    if (e_lfanew > 0x100000u) { std::fclose(f); return out; }

    if (std::fseek(f, static_cast<long>(e_lfanew), SEEK_SET) != 0) { std::fclose(f); return out; }
    std::uint8_t pe_hdr[26]{};
    if (std::fread(pe_hdr, 1, sizeof(pe_hdr), f) != sizeof(pe_hdr)) { std::fclose(f); return out; }
    if (pe_hdr[0] != 'P' || pe_hdr[1] != 'E' || pe_hdr[2] != 0 || pe_hdr[3] != 0) {
        std::fclose(f);
        return out;
    }

    const std::uint16_t machine =
        static_cast<std::uint16_t>(pe_hdr[4] | (pe_hdr[5] << 8));
    const std::uint16_t num_sections =
        static_cast<std::uint16_t>(pe_hdr[6] | (pe_hdr[7] << 8));
    const std::uint16_t opt_size =
        static_cast<std::uint16_t>(pe_hdr[20] | (pe_hdr[21] << 8));
    const std::uint16_t opt_magic =
        static_cast<std::uint16_t>(pe_hdr[24] | (pe_hdr[25] << 8));

    out.valid_pe = true;
    out.machine = machine;
    out.is_i386 = (machine == 0x014c);
    out.is_pe32 = (opt_magic == 0x010b);

    if (std::fseek(f, static_cast<long>(e_lfanew) + 24 + opt_size, SEEK_SET) == 0) {
        const std::uint16_t cap = std::min<std::uint16_t>(num_sections, 96);
        for (std::uint16_t i = 0; i < cap; ++i) {
            std::uint8_t sec[40]{};
            if (std::fread(sec, 1, sizeof(sec), f) != sizeof(sec)) break;
            if (std::memcmp(sec, ".bind\0\0\0", 8) == 0 || std::memcmp(sec, ".bind", 5) == 0) {
                out.has_bind_section = true;
            }
        }
    }
    std::fclose(f);
    return out;
}

const KnownBuild* find_known_build(const std::string& sha256) {
    for (const KnownBuild& b : kKnownBuilds) {
        if (sha256 == b.sha256) return &b;
    }
    return nullptr;
}

std::string quote_win_arg(const std::string& arg) {
    if (!arg.empty() && arg.find_first_of(" \t\n\v\"") == std::string::npos) return arg;
    std::string out = "\"";
    for (auto it = arg.begin();; ++it) {
        std::size_t backslashes = 0;
        while (it != arg.end() && *it == '\\') {
            ++backslashes;
            ++it;
        }
        if (it == arg.end()) {
            out.append(backslashes * 2, '\\');
            break;
        } else if (*it == '"') {
            out.append(backslashes * 2 + 1, '\\');
            out.push_back('"');
        } else {
            out.append(backslashes, '\\');
            out.push_back(*it);
        }
    }
    out.push_back('"');
    return out;
}

bool query_process_image_path(DWORD pid, std::string& out) {
    using QueryFullNameWFn = BOOL(WINAPI*)(HANDLE, DWORD, LPWSTR, PDWORD);
    HMODULE k32 = GetModuleHandleA("kernel32.dll");
    if (k32 == nullptr) return false;
    auto fn = reinterpret_cast<QueryFullNameWFn>(
        reinterpret_cast<void*>(GetProcAddress(k32, "QueryFullProcessImageNameW")));
    if (fn == nullptr) return false;
    HANDLE h = OpenProcess(PROCESS_QUERY_INFORMATION, FALSE, pid);
    if (h == nullptr) return false;
    std::wstring buf(4096, L'\0');
    DWORD sz = static_cast<DWORD>(buf.size());
    const BOOL ok = fn(h, 0, buf.data(), &sz);
    CloseHandle(h);
    if (!ok || sz == 0) return false;
    out = wide_to_utf8(buf.data(), static_cast<int>(sz));
    return !out.empty();
}

std::vector<DWORD> find_pids_by_name(const std::string& target_name, const std::string& full_path = {}) {
    std::vector<DWORD> exact;
    std::vector<DWORD> unknown_path;
    const std::wstring wname = utf8_to_wide(target_name);
    const std::wstring wfull = utf8_to_wide(full_path);
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE) return unknown_path;
    PROCESSENTRY32W pe{};
    pe.dwSize = sizeof(pe);
    if (Process32FirstW(snap, &pe)) {
        do {
            if (_wcsicmp(pe.szExeFile, wname.c_str()) == 0) {
                if (!wfull.empty()) {
                    std::string proc_path;
                    if (query_process_image_path(pe.th32ProcessID, proc_path)) {
                        const std::wstring wproc = utf8_to_wide(proc_path);
                        if (_wcsicmp(wproc.c_str(), wfull.c_str()) == 0) {
                            exact.push_back(pe.th32ProcessID);
                        }
                        continue;
                    }
                }
                unknown_path.push_back(pe.th32ProcessID);
            }
        } while (Process32NextW(snap, &pe));
    }
    CloseHandle(snap);
    return !exact.empty() ? exact : unknown_path;
}

bool module_loaded_in_pid(DWORD pid, const std::string& module_basename) {
    HANDLE snap = INVALID_HANDLE_VALUE;
    for (int attempt = 0; attempt < 16; ++attempt) {
        snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
        if (snap != INVALID_HANDLE_VALUE) break;
        const DWORD err = GetLastError();
        if (err != ERROR_BAD_LENGTH && err != ERROR_PARTIAL_COPY) return false;
        Sleep(25);
    }
    if (snap == INVALID_HANDLE_VALUE) return false;
    const std::wstring wmod = utf8_to_wide(module_basename);
    const std::wstring wruntime = utf8_to_wide(kp::naming::kRuntimeDll);
    const std::wstring wlegacy = utf8_to_wide(kp::naming::kLegacyRuntimeDll);
    MODULEENTRY32W me{};
    me.dwSize = sizeof(me);
    bool found = false;
    if (Module32FirstW(snap, &me)) {
        do {
            if (_wcsicmp(me.szModule, wruntime.c_str()) == 0 ||
                _wcsicmp(me.szModule, wlegacy.c_str()) == 0 ||
                (!wmod.empty() && _wcsicmp(me.szModule, wmod.c_str()) == 0)) {
                found = true;
                break;
            }
        } while (Module32NextW(snap, &me));
    }
    CloseHandle(snap);
    return found;
}

struct WindowSearch {
    DWORD pid = 0;
    bool found = false;
};

BOOL CALLBACK enum_visible_window_cb(HWND hwnd, LPARAM lparam) {
    auto* ws = reinterpret_cast<WindowSearch*>(lparam);
    DWORD win_pid = 0;
    GetWindowThreadProcessId(hwnd, &win_pid);
    if (win_pid == ws->pid && IsWindowVisible(hwnd)) {
        ws->found = true;
        return FALSE;
    }
    return TRUE;
}

bool has_visible_window(DWORD pid) {
    WindowSearch ws{pid, false};
    EnumWindows(enum_visible_window_cb, reinterpret_cast<LPARAM>(&ws));
    return ws.found;
}

bool check_wow64_parity(HANDLE target) {
    using IsWow64Fn = BOOL(WINAPI*)(HANDLE, PBOOL);
    HMODULE k32 = GetModuleHandleA("kernel32.dll");
    if (k32 == nullptr) return true;
    auto fn = reinterpret_cast<IsWow64Fn>(
        reinterpret_cast<void*>(GetProcAddress(k32, "IsWow64Process")));
    if (fn == nullptr) return true;
    BOOL self_wow64 = FALSE;
    BOOL target_wow64 = FALSE;
    if (!fn(GetCurrentProcess(), &self_wow64) || !fn(target, &target_wow64)) return false;
    return self_wow64 == target_wow64;
}

LPCVOID find_main_module_base(DWORD pid) {
    for (int attempt = 0; attempt < 8; ++attempt) {
        HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid);
        if (snap == INVALID_HANDLE_VALUE) {
            const DWORD err = GetLastError();
            if (err == ERROR_BAD_LENGTH || err == ERROR_PARTIAL_COPY) {
                Sleep(20);
                continue;
            }
            break;
        }
        MODULEENTRY32 me{};
        me.dwSize = sizeof(me);
        const BOOL ok = Module32First(snap, &me);
        CloseHandle(snap);
        if (ok && me.modBaseAddr != nullptr) return me.modBaseAddr;
        break;
    }
    return reinterpret_cast<LPCVOID>(static_cast<std::uintptr_t>(0x00400000u));
}

bool check_target_pe32(HANDLE proc, DWORD pid) {
    if (!check_wow64_parity(proc)) return false;
    const LPCVOID base = find_main_module_base(pid);
    std::uint8_t dos[0x40]{};
    SIZE_T read = 0;
    if (!ReadProcessMemory(proc, base, dos, sizeof(dos), &read) || read != sizeof(dos) ||
        dos[0] != 'M' || dos[1] != 'Z') {
        return false;
    }
    const std::uint32_t e_lfanew = static_cast<std::uint32_t>(dos[0x3c]) |
                                   (static_cast<std::uint32_t>(dos[0x3d]) << 8) |
                                   (static_cast<std::uint32_t>(dos[0x3e]) << 16) |
                                   (static_cast<std::uint32_t>(dos[0x3f]) << 24);
    if (e_lfanew < sizeof(dos) || e_lfanew >= 0x100000u) return false;
    std::uint8_t pe_hdr[26]{};
    const auto nt_addr = reinterpret_cast<LPCVOID>(reinterpret_cast<std::uintptr_t>(base) + e_lfanew);
    if (!ReadProcessMemory(proc, nt_addr, pe_hdr, sizeof(pe_hdr), &read) || read != sizeof(pe_hdr)) {
        return false;
    }
    if (pe_hdr[0] != 'P' || pe_hdr[1] != 'E' || pe_hdr[2] != 0 || pe_hdr[3] != 0) return false;
    const std::uint16_t machine = static_cast<std::uint16_t>(pe_hdr[4] | (pe_hdr[5] << 8));
    const std::uint16_t opt_magic = static_cast<std::uint16_t>(pe_hdr[24] | (pe_hdr[25] << 8));
    return machine == 0x014c && opt_magic == 0x010b;
}

bool inject_dll(HANDLE proc, const std::string& abs_dll_path, std::string& err) {
    HMODULE k32 = GetModuleHandleA("kernel32.dll");
    if (k32 == nullptr) {
        err = "GetModuleHandleA(kernel32.dll) failed";
        return false;
    }
    const FARPROC load_lib = GetProcAddress(k32, "LoadLibraryW");
    if (load_lib == nullptr) {
        err = "GetProcAddress(LoadLibraryW) failed";
        return false;
    }

    const std::wstring wdll = utf8_to_wide(abs_dll_path);
    if (wdll.empty()) {
        err = "invalid DLL path: " + abs_dll_path;
        return false;
    }
    const SIZE_T len = (wdll.size() + 1) * sizeof(wchar_t);
    void* remote = VirtualAllocEx(proc, nullptr, len, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE);
    if (remote == nullptr) {
        err = "VirtualAllocEx failed (err=" + std::to_string(GetLastError()) + ")";
        return false;
    }

    SIZE_T written = 0;
    if (!WriteProcessMemory(proc, remote, wdll.c_str(), len, &written) || written != len) {
        err = "WriteProcessMemory failed (err=" + std::to_string(GetLastError()) + ")";
        VirtualFreeEx(proc, remote, 0, MEM_RELEASE);
        return false;
    }

    HANDLE thread = CreateRemoteThread(
        proc, nullptr, 0,
        reinterpret_cast<LPTHREAD_START_ROUTINE>(reinterpret_cast<void*>(load_lib)),
        remote, 0, nullptr);
    if (thread == nullptr) {
        err = "CreateRemoteThread failed (err=" + std::to_string(GetLastError()) + ")";
        VirtualFreeEx(proc, remote, 0, MEM_RELEASE);
        return false;
    }

    const DWORD wait_rc = WaitForSingleObject(thread, 15000);
    if (wait_rc != WAIT_OBJECT_0) {
        CloseHandle(thread);
        // Never VirtualFreeEx(remote) on timeout while remote thread may still read it.
        err = "remote LoadLibraryW did not finish within 15s (wait=" + std::to_string(wait_rc) + ")";
        return false;
    }
    DWORD exit_code = 0;
    const BOOL got_code = GetExitCodeThread(thread, &exit_code);
    CloseHandle(thread);
    VirtualFreeEx(proc, remote, 0, MEM_RELEASE);

    if (!got_code || exit_code == 0) {
        err = "remote LoadLibraryW returned NULL for " + abs_dll_path;
        return false;
    }
    return true;
}

int wait_for_exit_code(HANDLE proc) {
    if (WaitForSingleObject(proc, INFINITE) != WAIT_OBJECT_0) {
        std::fprintf(stderr, "error: WaitForSingleObject failed (err=%lu)\n",
                     static_cast<unsigned long>(GetLastError()));
        return 1;
    }
    DWORD code = 0;
    if (!GetExitCodeProcess(proc, &code)) {
        std::fprintf(stderr, "error: GetExitCodeProcess failed (err=%lu)\n",
                     static_cast<unsigned long>(GetLastError()));
        return 1;
    }
    return static_cast<int>(code);
}

const char* mode_name(Mode m) {
    switch (m) {
        case Mode::Auto:   return "auto";
        case Mode::Direct: return "direct";
        case Mode::Steam:  return "steam";
        case Mode::Attach: return "attach";
    }
    return "unknown";
}

void print_help() {
    std::printf(
        "Usage: kotorjit-launch [options] [game-exe] [-- <game-args...>]\n"
        "\n"
        "Runtime DLL injector for KotorJIT (replaces binkw32.dll proxy on native Windows).\n"
        "\n"
        "Options:\n"
        "  --mode auto|direct|steam|attach  Injection mode (default: auto)\n"
        "  --dll <path>                     Path to kotorjit.dll (auto-detected if omitted)\n"
        "  --pid <pid>                      Attach to running process ID (implies --mode attach)\n"
        "  --timeout <ms>                   Steam/window wait timeout in ms (default: 60000)\n"
        "  --no-wait-window                 In steam mode, inject without waiting for a visible window\n"
        "  --wait                           Wait for the game process to exit\n"
        "  --check                          Inspect target executable and print plan without launching\n"
        "  --version                        Print version and exit\n"
        "  -h, --help                       Show this help\n");
}

std::vector<std::string> collect_args(int argc, char** argv) {
    std::vector<std::string> out;
    int wargc = 0;
    if (LPWSTR* wargv = CommandLineToArgvW(GetCommandLineW(), &wargc); wargv != nullptr) {
        out.reserve(static_cast<std::size_t>(wargc));
        for (int i = 0; i < wargc; ++i) out.push_back(wide_to_utf8(wargv[i]));
        LocalFree(wargv);
        return out;
    }
    out.reserve(static_cast<std::size_t>(argc));
    for (int i = 0; i < argc; ++i) out.emplace_back(argv[i]);
    return out;
}

bool parse_args(const std::vector<std::string>& args, Options& opt, bool& exit_early, int& exit_code) {
    exit_early = false;
    exit_code = 0;
    for (std::size_t i = 1; i < args.size(); ++i) {
        const std::string& a = args[i];
        if (a == "--") {
            for (std::size_t j = i + 1; j < args.size(); ++j) opt.game_args.emplace_back(args[j]);
            break;
        }
        if (a == "-h" || a == "--help") {
            print_help();
            exit_early = true;
            return true;
        }
        if (a == "--version") {
            std::printf("kotorjit-launch %s\n", kVersion);
            exit_early = true;
            return true;
        }
        if (a == "--wait") {
            opt.wait = true;
            continue;
        }
        if (a == "--no-wait-window") {
            opt.wait_window = false;
            continue;
        }
        if (a == "--check") {
            opt.check_only = true;
            continue;
        }
        if (a == "--mode" || a == "--dll" || a == "--pid" || a == "--timeout") {
            if (i + 1 >= args.size()) {
                std::fprintf(stderr, "error: %s requires a value\n", a.c_str());
                return false;
            }
            const std::string& val = args[++i];
            if (a == "--mode") {
                const std::string m = to_lower_ascii(val);
                if (m == "auto") opt.mode = Mode::Auto;
                else if (m == "direct") opt.mode = Mode::Direct;
                else if (m == "steam") opt.mode = Mode::Steam;
                else if (m == "attach") opt.mode = Mode::Attach;
                else {
                    std::fprintf(stderr, "error: unknown --mode '%s' (expected auto, direct, steam, attach)\n", m.c_str());
                    return false;
                }
            } else if (a == "--dll") {
                opt.dll_path = val;
            } else if (a == "--pid") {
                unsigned long v = 0;
                if (!parse_uint_dec(val.c_str(), v) || v == 0 ||
                    v > static_cast<unsigned long>((std::numeric_limits<DWORD>::max)())) {
                    std::fprintf(stderr, "error: invalid --pid value\n");
                    return false;
                }
                opt.pid = static_cast<DWORD>(v);
                opt.mode = Mode::Attach;
            } else if (a == "--timeout") {
                unsigned long v = 0;
                if (!parse_uint_dec(val.c_str(), v) || v == 0 ||
                    v > static_cast<unsigned long>((std::numeric_limits<DWORD>::max)())) {
                    std::fprintf(stderr, "error: invalid --timeout value\n");
                    return false;
                }
                opt.timeout_ms = static_cast<DWORD>(v);
            }
            continue;
        }
        if (!a.empty() && a[0] == '-') {
            std::fprintf(stderr, "error: unknown option '%s'\n", a.c_str());
            return false;
        }
        if (!opt.exe_path.empty()) {
            std::fprintf(stderr, "error: unexpected extra positional argument '%s'\n", a.c_str());
            return false;
        }
        opt.exe_path = a;
    }
    return true;
}

std::string resolve_default_exe(const std::string& launcher_dir) {
    for (const char* name : {"swkotor.exe", "swkotor2.exe"}) {
        const std::string cand = join_win(launcher_dir, name);
        if (file_exists(cand)) return abs_path_of(cand);
    }
    return {};
}

std::string resolve_dll(const Options& opt, const std::string& game_dir, const std::string& launcher_dir) {
    if (!opt.dll_path.empty()) return abs_path_of(opt.dll_path);
    const std::string cands[] = {
        join_win(game_dir, kp::naming::kRuntimeDll),
        join_win(launcher_dir, kp::naming::kRuntimeDll),
        join_win(game_dir, kp::naming::kLegacyRuntimeDll),
        join_win(launcher_dir, kp::naming::kLegacyRuntimeDll),
    };
    for (const std::string& c : cands) {
        if (!game_dir.empty() || c.rfind(launcher_dir, 0) == 0) {
            if (file_exists(c)) return abs_path_of(c);
        }
    }
    return {};
}

int run_direct(const std::string& exe_path, const std::string& game_dir,
               const std::string& dll_path, const Options& opt) {
    std::string cmd = quote_win_arg(exe_path);
    for (const std::string& arg : opt.game_args) {
        cmd += ' ';
        cmd += quote_win_arg(arg);
    }
    std::wstring wexe = utf8_to_wide(exe_path);
    std::wstring wcmd = utf8_to_wide(cmd);
    std::wstring wdir = utf8_to_wide(game_dir);
    std::vector<wchar_t> cmd_buf(wcmd.begin(), wcmd.end());
    cmd_buf.push_back(L'\0');

    STARTUPINFOW si{};
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi{};
    if (!CreateProcessW(wexe.c_str(), cmd_buf.data(), nullptr, nullptr, FALSE,
                        CREATE_SUSPENDED, nullptr, wdir.c_str(), &si, &pi)) {
        std::fprintf(stderr, "error: CreateProcessW('%s') failed (err=%lu)\n",
                     exe_path.c_str(), static_cast<unsigned long>(GetLastError()));
        return 1;
    }

    std::string err;
    if (!inject_dll(pi.hProcess, dll_path, err)) {
        std::fprintf(stderr, "error: %s\n", err.c_str());
        TerminateProcess(pi.hProcess, 1);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return 1;
    }

    if (ResumeThread(pi.hThread) == static_cast<DWORD>(-1)) {
        std::fprintf(stderr, "error: ResumeThread failed (err=%lu)\n",
                     static_cast<unsigned long>(GetLastError()));
        TerminateProcess(pi.hProcess, 1);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        return 1;
    }

    std::printf("injected %s into PID %lu (direct suspended launch)\n",
                dll_path.c_str(), static_cast<unsigned long>(pi.dwProcessId));
    CloseHandle(pi.hThread);

    int rc = 0;
    if (opt.wait) rc = wait_for_exit_code(pi.hProcess);
    CloseHandle(pi.hProcess);
    return rc;
}

int run_steam(const std::string& exe_path, const std::string& game_dir,
              const std::string& dll_path, const KnownBuild* known, const Options& opt) {
    const std::string exe_name = basename_of(exe_path);
    const std::vector<DWORD> existing = find_pids_by_name(exe_name, exe_path);

    std::string target = exe_path;
    if (known != nullptr && known->steam_app_id[0] != '\0') {
        if (!opt.game_args.empty()) {
            std::fprintf(stderr,
                         "warning: steam://rungameid/%s launch ignores extra arguments after '--'\n",
                         known->steam_app_id);
        }
        target = std::string("steam://rungameid/") + known->steam_app_id;
    }

    const std::wstring wtarget = utf8_to_wide(target);
    const std::wstring wdir = utf8_to_wide(game_dir);
    const HINSTANCE shell_rc = ShellExecuteW(
        nullptr, L"open", wtarget.c_str(), nullptr, wdir.c_str(), SW_SHOWNORMAL);
    if (reinterpret_cast<std::uintptr_t>(shell_rc) <= 32u) {
        std::fprintf(stderr, "error: ShellExecuteW('%s') failed (code=%lu)\n",
                     target.c_str(), static_cast<unsigned long>(reinterpret_cast<std::uintptr_t>(shell_rc)));
        return 1;
    }

    const std::uint64_t start_ms = tick_now_ms();
    HANDLE target_proc = nullptr;
    DWORD target_pid = 0;
    std::vector<DWORD> tried_pids = existing;

    while (tick_now_ms() - start_ms < opt.timeout_ms) {
        const std::vector<DWORD> now_pids = find_pids_by_name(exe_name, exe_path);
        for (DWORD pid : now_pids) {
            if (std::find(tried_pids.begin(), tried_pids.end(), pid) != tried_pids.end()) continue;
            HANDLE proc = OpenProcess(
                PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION |
                PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ | SYNCHRONIZE,
                FALSE, pid);
            if (proc == nullptr) continue;
            if (!check_target_pe32(proc, pid)) {
                CloseHandle(proc);
                continue;
            }
            // SteamStub bootstrapper often exits cleanly and spawns the unwrapped game
            // process within a few hundred milliseconds; sleep 500 ms and verify.
            Sleep(500);
            if (WaitForSingleObject(proc, 0) != WAIT_TIMEOUT) {
                CloseHandle(proc);
                tried_pids.push_back(pid);
                continue;
            }
            target_proc = proc;
            target_pid = pid;
            break;
        }
        if (target_proc != nullptr) break;
        Sleep(100);
    }

    if (target_proc == nullptr) {
        std::fprintf(stderr, "error: timed out after %lu ms waiting for %s to start\n",
                     static_cast<unsigned long>(opt.timeout_ms), exe_name.c_str());
        return 1;
    }

    if (opt.wait_window) {
        bool win_ready = false;
        while (tick_now_ms() - start_ms < opt.timeout_ms) {
            if (target_proc != nullptr && WaitForSingleObject(target_proc, 0) != WAIT_TIMEOUT) {
                CloseHandle(target_proc);
                target_proc = nullptr;
                tried_pids.push_back(target_pid);
            }
            if (target_proc == nullptr) {
                // Bootstrapper exited later than 500 ms; look for replacement PID.
                const std::vector<DWORD> now_pids = find_pids_by_name(exe_name, exe_path);
                for (DWORD pid : now_pids) {
                    if (std::find(tried_pids.begin(), tried_pids.end(), pid) != tried_pids.end()) {
                        continue;
                    }
                    HANDLE proc = OpenProcess(
                        PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION |
                        PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ | SYNCHRONIZE,
                        FALSE, pid);
                    if (proc != nullptr && check_target_pe32(proc, pid)) {
                        target_proc = proc;
                        target_pid = pid;
                        break;
                    }
                    if (proc != nullptr) CloseHandle(proc);
                }
                if (target_proc == nullptr) {
                    Sleep(100);
                    continue;
                }
            }
            if (has_visible_window(target_pid)) {
                win_ready = true;
                break;
            }
            Sleep(100);
        }

        if (target_proc == nullptr) {
            std::fprintf(stderr, "error: %s exited before exposing a main window\n", exe_name.c_str());
            return 1;
        }
        if (!win_ready) {
            std::fprintf(stderr, "error: timed out waiting for visible window on PID %lu\n",
                         static_cast<unsigned long>(target_pid));
            CloseHandle(target_proc);
            return 1;
        }
    }

    const std::string dll_name = basename_of(dll_path);
    if (module_loaded_in_pid(target_pid, dll_name)) {
        std::fprintf(stderr, "error: %s is already loaded in PID %lu\n",
                     dll_name.c_str(), static_cast<unsigned long>(target_pid));
        CloseHandle(target_proc);
        return 1;
    }

    std::string err;
    if (!inject_dll(target_proc, dll_path, err)) {
        std::fprintf(stderr, "error: %s\n", err.c_str());
        CloseHandle(target_proc);
        return 1;
    }

    std::printf("injected %s into PID %lu (steam delayed launch)\n",
                dll_path.c_str(), static_cast<unsigned long>(target_pid));

    int rc = 0;
    if (opt.wait) rc = wait_for_exit_code(target_proc);
    CloseHandle(target_proc);
    return rc;
}

int run_attach(const std::string& exe_path, const std::string& dll_path, const Options& opt) {
    DWORD pid = opt.pid;
    if (pid == 0) {
        const std::string exe_name = basename_of(exe_path);
        const std::vector<DWORD> pids = find_pids_by_name(exe_name, exe_path);
        if (pids.empty()) {
            std::fprintf(stderr, "error: no running process matching '%s'\n", exe_name.c_str());
            return 1;
        }
        if (pids.size() > 1) {
            std::fprintf(stderr, "error: multiple processes match '%s'; pass --pid\n", exe_name.c_str());
            return 1;
        }
        pid = pids.front();
    }

    HANDLE proc = OpenProcess(
        PROCESS_CREATE_THREAD | PROCESS_QUERY_INFORMATION |
        PROCESS_VM_OPERATION | PROCESS_VM_WRITE | PROCESS_VM_READ | SYNCHRONIZE,
        FALSE, pid);
    if (proc == nullptr) {
        std::fprintf(stderr, "error: OpenProcess(%lu) failed (err=%lu)\n",
                     static_cast<unsigned long>(pid), static_cast<unsigned long>(GetLastError()));
        return 1;
    }
    if (!check_target_pe32(proc, pid)) {
        std::fprintf(stderr, "error: PID %lu is not a valid 32-bit PE process\n",
                     static_cast<unsigned long>(pid));
        CloseHandle(proc);
        return 1;
    }

    const std::string dll_name = basename_of(dll_path);
    if (module_loaded_in_pid(pid, dll_name)) {
        std::fprintf(stderr, "error: %s is already loaded in PID %lu\n",
                     dll_name.c_str(), static_cast<unsigned long>(pid));
        CloseHandle(proc);
        return 1;
    }

    std::string err;
    if (!inject_dll(proc, dll_path, err)) {
        std::fprintf(stderr, "error: %s\n", err.c_str());
        CloseHandle(proc);
        return 1;
    }

    std::printf("injected %s into PID %lu (attach)\n",
                dll_path.c_str(), static_cast<unsigned long>(pid));

    int rc = 0;
    if (opt.wait) rc = wait_for_exit_code(proc);
    CloseHandle(proc);
    return rc;
}

}  // namespace

int main(int argc, char** argv) {
    const std::vector<std::string> args = collect_args(argc, argv);
    Options opt;
    bool exit_early = false;
    int parse_rc = 0;
    if (!parse_args(args, opt, exit_early, parse_rc)) return 2;
    if (exit_early) return parse_rc;

    const std::string launcher_dir = self_dir();
    std::string exe_path;
    std::string game_dir;
    if (!opt.exe_path.empty()) {
        exe_path = abs_path_of(opt.exe_path);
        game_dir = dirname_of(exe_path);
    } else if (opt.pid == 0) {
        exe_path = resolve_default_exe(launcher_dir);
        game_dir = exe_path.empty() ? launcher_dir : dirname_of(exe_path);
    } else if (query_process_image_path(opt.pid, exe_path)) {
        exe_path = abs_path_of(exe_path);
        game_dir = dirname_of(exe_path);
    } else {
        game_dir = launcher_dir;
    }

    if (opt.pid == 0 && (exe_path.empty() || !file_exists(exe_path))) {
        std::fprintf(stderr,
                     "error: game executable not found (pass <game-exe> or place beside swkotor.exe / swkotor2.exe)\n");
        return 1;
    }

    const std::string dll_path = resolve_dll(opt, game_dir, launcher_dir);
    if (dll_path.empty() || !file_exists(dll_path)) {
        std::fprintf(stderr, "error: %s not found next to game or launcher (or via --dll)\n",
                     kp::naming::kRuntimeDll);
        return 1;
    }

    PeInspection pe;
    std::string sha256;
    const KnownBuild* known = nullptr;
    if (!exe_path.empty()) {
        pe = inspect_pe(exe_path);
        if (!pe.valid_pe) {
            std::fprintf(stderr, "error: %s is not a valid PE executable\n", exe_path.c_str());
            return 1;
        }
        if (!pe.is_i386 || !pe.is_pe32) {
            std::fprintf(stderr, "error: %s is not a valid 32-bit PE32 executable (machine=0x%04x)\n",
                         exe_path.c_str(), static_cast<unsigned>(pe.machine));
            return 1;
        }
        sha256 = kp::image::sha256_file(exe_path);
        known = find_known_build(sha256);
    }

    Mode resolved = opt.mode;
    if (resolved == Mode::Auto) {
        if ((known != nullptr && known->steam_packed) || pe.has_bind_section) {
            resolved = Mode::Steam;
        } else {
            resolved = Mode::Direct;
        }
    }

    const bool wine = running_under_wine();
    const bool proxy_present = !game_dir.empty() && looks_like_kotorjit_proxy(join_win(game_dir, "binkw32.dll"));

    if (wine) {
        std::fprintf(stderr,
                     "warning: running under Wine/Proton; the binkw32.dll proxy (--method proxy) is recommended here\n");
    }
    if (proxy_present && resolved != Mode::Attach) {
        std::fprintf(stderr,
                     "warning: binkw32.dll in %s is already a KotorJIT proxy; runtime injection is redundant\n",
                     game_dir.c_str());
    }
    if (resolved == Mode::Steam) {
        std::fprintf(stderr,
                     "note: packed Steam build detected (.bind/SteamStub); using delayed Steam attach "
                     "(binkw32.dll proxy is also supported)\n");
    }

    if (opt.check_only) {
        std::printf("exe: %s\n", exe_path.empty() ? "(pid attach)" : exe_path.c_str());
        std::printf("sha256: %s\n", sha256.empty() ? "(n/a)" : sha256.c_str());
        std::printf("build: %s\n", known != nullptr ? known->alias : "unknown");
        std::printf("steam_stub: %s\n", ((known != nullptr && known->steam_packed) || pe.has_bind_section) ? "yes" : "no");
        std::printf("mode: %s\n", mode_name(resolved));
        std::printf("dll: %s\n", dll_path.c_str());
        std::printf("proxy_present: %s\n", proxy_present ? "yes" : "no");
        std::printf("wine: %s\n", wine ? "yes" : "no");
        return 0;
    }

    switch (resolved) {
        case Mode::Direct: return run_direct(exe_path, game_dir, dll_path, opt);
        case Mode::Steam:  return run_steam(exe_path, game_dir, dll_path, known, opt);
        case Mode::Attach: return run_attach(exe_path, dll_path, opt);
        case Mode::Auto:   return 1;
    }
    return 1;
}
