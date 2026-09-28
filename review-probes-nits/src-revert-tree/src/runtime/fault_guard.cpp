// Turning a hardware fault inside our own code into a logged, contained
// failure.
//
// guard() in hooks/thiscall.hpp catches C++ exceptions, and says plainly that
// it does not catch an access violation. This is the other half. A null
// dereference in a hook body is not a C++ exception, so without this file it
// sails past guard() and takes the game's process down -- which the player
// reports as the game being broken, not as the mod being broken.
//
// WHAT WE CLAIM, AND WHAT WE MUST NOT
// ===================================
// A fault is ours only while a hook body is running its OWN work. A fault in
// the game's code is the game's business: claiming it would swallow a crash we
// did not cause, hide a real bug from whoever is debugging the game, and
// pre-empt the game's own __except handlers. So the handler asks in_hook_body()
// first and passes everything else through untouched.
//
// That is also why hook bodies disarm before calling the original. The original
// runs game code -- for MainLoop, the entire server frame -- and a fault in it
// must reach the game's handlers exactly as it would without us.
//
// HOW THE RECOVERY WORKS
// ======================
// The handler does not try to fix the faulting instruction. It rewrites the
// resumption address to a bail stub and returns; the OS resumes the thread
// there through the normal path (NtContinue on Windows, sigreturn on Linux)
// rather than us reaching into the thread from inside a handler. The stub then
// longjmps to the recovery point the hook body armed on entry, and the body
// returns the fallback value it declared. The engine sees an ordinary return.
//
// WHAT THIS CANNOT RECOVER FROM -- stated, not implied
// ====================================================
//   * A stack overflow. The bail stub needs stack to run on, and there is none
//     left. The process dies, as it would have anyway.
//   * A fault that has already corrupted game state. We restore control flow,
//     never data. If the body wrote a bad pointer before it faulted, that write
//     already happened.
//   * Anything a longjmp skips. Jumping out of a C++ frame does not run
//     destructors, so whatever the body had allocated leaks, and a lua_State
//     faulted mid-pcall is left with an inconsistent stack. That is why a fault
//     inside dispatch takes the whole runtime out of service (set_live(false))
//     rather than merely poisoning one site.
//   * A fault on a thread that is inside a hook body but faulting for an
//     unrelated reason. We would claim it. The window is small because bodies
//     disarm around the original, but it is not zero.
//
// A poisoned site never runs our work again for the life of the process. That
// is deliberate: a body that faulted once will fault again, and the second
// recovery is not more informative than the first.
//
// The runtime-wide stop is not permanent, though. `lua reload` in the console
// rebuilds every lua_State and re-arms dispatch, which is sound precisely
// because the states were the part left inconsistent. Poison does not lift.
#include "runtime/internal.hpp"

#include <csetjmp>
#include <cstddef>
#include <cstring>

#if defined(_WIN32)
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#else
#include <csignal>
#include <fcntl.h>
#include <ucontext.h>
#include <unistd.h>
#endif

namespace kp::runtime {
namespace {

// Eight is past the point of usefulness: a hook body calling the original of
// another hooked site is one level, and nothing in the design nests further.
// The cap exists so the per-thread cost is a fixed array rather than a
// container that would allocate on a game thread.
constexpr int kMaxDepth = 8;

struct ThreadFrames {
    jmp_buf            bufs[kMaxDepth];
    jmp_buf            scratch;          // used past the cap; never jumped to
    const char*        sites[kMaxDepth];
    std::atomic<bool>* poisons[kMaxDepth];
    // Whether the frame at this depth ran setjmp. enter_hook_body() makes
    // in_hook_body() true without arming anything, so "we are in a hook body"
    // and "there is somewhere to jump to" are two different questions and the
    // handler has to ask the second one.
    bool               armed[kMaxDepth];
    int                depth = 0;
    // Filled by the handler, read by note_fault(). The handler runs where
    // formatting is unsafe, so it records and the normal context explains.
    std::uintptr_t     fault_addr = 0;
    std::uintptr_t     fault_pc = 0;
    unsigned long      fault_code = 0;
};

// POD only, so this stays native thread-local storage rather than the
// emutls/__cxa_thread_atexit path a non-trivial destructor would drag in. That
// matters here: this DLL is loaded with LoadLibrary, and the simpler the TLS,
// the fewer loader behaviours we depend on.
thread_local ThreadFrames t_frames;

char g_log_path[512] = {0};

// --------------------------------------------------- async-safe reporting ---
//
// Everything below runs inside a signal handler or a vectored exception
// handler. No printf, no heap, no locks: the thread that faulted may already
// hold the CRT's lock, and taking it again is a deadlock instead of a
// diagnostic.

std::size_t append_str(char* out, std::size_t cap, std::size_t at, const char* s) {
    while (*s != '\0' && at + 1 < cap) out[at++] = *s++;
    return at;
}

std::size_t append_hex(char* out, std::size_t cap, std::size_t at, std::uintptr_t v) {
    static const char kDigits[] = "0123456789abcdef";
    at = append_str(out, cap, at, "0x");
    bool leading = true;
    for (int shift = 28; shift >= 0; shift -= 4) {
        const unsigned nib = (v >> shift) & 0xfu;
        if (leading && nib == 0 && shift != 0) continue;
        leading = false;
        if (at + 1 < cap) out[at++] = kDigits[nib];
    }
    return at;
}

void emit(const char* line, std::size_t len) {
#if defined(_WIN32)
    HANDLE f = CreateFileA(g_log_path[0] ? g_log_path : "kotorphasor.log",
                           FILE_APPEND_DATA, FILE_SHARE_READ | FILE_SHARE_WRITE,
                           nullptr, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (f == INVALID_HANDLE_VALUE) return;
    DWORD written = 0;
    WriteFile(f, line, static_cast<DWORD>(len), &written, nullptr);
    CloseHandle(f);
#else
    const int fd = ::open(g_log_path[0] ? g_log_path : "kotorphasor.log",
                          O_WRONLY | O_CREAT | O_APPEND, 0644);
    if (fd < 0) return;
    const ssize_t ignored = ::write(fd, line, len);
    (void)ignored;
    ::close(fd);
#endif
}

void report(const char* what, const char* site, std::uintptr_t addr,
            std::uintptr_t pc, std::uintptr_t code) {
    char line[320];
    std::size_t at = 0;
    at = append_str(line, sizeof line, at, "[fault] ");
    at = append_str(line, sizeof line, at, what);
    at = append_str(line, sizeof line, at, " site=");
    at = append_str(line, sizeof line, at, site ? site : "(none)");
    at = append_str(line, sizeof line, at, " code=");
    at = append_hex(line, sizeof line, at, code);
    at = append_str(line, sizeof line, at, " at=");
    at = append_hex(line, sizeof line, at, addr);
    at = append_str(line, sizeof line, at, " pc=");
    at = append_hex(line, sizeof line, at, pc);
    at = append_str(line, sizeof line, at, "\n");
    emit(line, at);
}

// The stack words around a fault, which is enough to name the return chain
// when a call went somewhere it should not have. A few words BELOW the pointer
// come first: an instruction that faulted after popping still has what it
// popped sitting there, and that is usually where the return address is.
// Reads are probed first -- the stack pointer at a fault is not always a stack
// pointer.
constexpr int kStackWordsBelow = 12;
constexpr int kStackWords = 10;

#if defined(_WIN32)
int g_passthrough_reports = 0;
constexpr int kMaxPassthroughReports = 8;

void report_stack(std::uintptr_t sp) {
    if (sp == 0) return;
    char line[512];
    std::size_t at = 0;
    at = append_str(line, sizeof line, at, "[fault] stack sp=");
    at = append_hex(line, sizeof line, at, sp);
    for (int i = -kStackWordsBelow; i < kStackWords; ++i) {
        const void* p = reinterpret_cast<const void*>(sp + static_cast<std::uintptr_t>(i * 4));
        if (!platform::is_readable(p, 4)) continue;
        if (i == 0) at = append_str(line, sizeof line, at, " |");
        std::uint32_t w = 0;
        std::memcpy(&w, p, sizeof w);
        at = append_str(line, sizeof line, at, " ");
        at = append_hex(line, sizeof line, at, w);
    }
    at = append_str(line, sizeof line, at, "\n");
    emit(line, at);
}
#endif

// --------------------------------------------------------------- claiming ---

// Decide whether this fault is ours and record what the bail path will report.
// Returns the resumption address to install, or 0 to pass the fault through.
std::uintptr_t claim(std::uintptr_t addr, std::uintptr_t pc, unsigned long code);

bool g_installed = false;

}  // namespace

// The bail stub. The OS resumes the faulting thread here with every register
// but EIP as it was, so longjmp finds the same stack it was armed on.
//
// extern "C" and a plain function on purpose: it is entered by having its
// address written into a CONTEXT, so there is no return address below ESP and
// nothing it may assume about its caller. It never returns.
extern "C" void kp_fault_bail(void);

extern "C" void kp_fault_bail(void) {
    ThreadFrames& tf = t_frames;
    const int idx = tf.depth - 1;
    if (idx < 0 || idx >= kMaxDepth) {
        // claim() refused to claim in this case, so reaching here means the
        // frame stack changed underneath us. There is nowhere to jump to.
        report("unrecoverable", "(no armed frame)", tf.fault_addr, tf.fault_pc, tf.fault_code);
#if defined(_WIN32)
        TerminateProcess(GetCurrentProcess(), 0xC0000005u);
#else
        _exit(139);
#endif
    }
    std::longjmp(tf.bufs[idx], 1);
}

namespace {

std::uintptr_t claim(std::uintptr_t addr, std::uintptr_t pc, unsigned long code) {
    ThreadFrames& tf = t_frames;
    if (tf.depth <= 0 || tf.depth > kMaxDepth) return 0;   // not ours

    // Inside a hook body but with no recovery point armed. Claiming would mean
    // longjmp-ing through an uninitialised buffer, which is a worse crash than
    // the one we were asked to contain.
    if (!tf.armed[tf.depth - 1]) return 0;

    tf.fault_addr = addr;
    tf.fault_pc = pc;
    tf.fault_code = code;
    report("caught in hook body", tf.sites[tf.depth - 1], addr, pc, code);
    return reinterpret_cast<std::uintptr_t>(&kp_fault_bail);
}

#if defined(_WIN32)

// Only faults a hook body could plausibly cause. A C++ throw is an exception
// too (0xE06D7363) and guard() already owns that one, so filtering by code
// keeps the two mechanisms from fighting over the same event.
bool is_hardware_fault(DWORD code) {
    switch (code) {
    case EXCEPTION_ACCESS_VIOLATION:
    case EXCEPTION_DATATYPE_MISALIGNMENT:
    case EXCEPTION_ILLEGAL_INSTRUCTION:
    case EXCEPTION_PRIV_INSTRUCTION:
    case EXCEPTION_IN_PAGE_ERROR:
    case EXCEPTION_INT_DIVIDE_BY_ZERO:
    case EXCEPTION_INT_OVERFLOW:
        return true;
    default:
        return false;
    }
}

PVOID g_veh = nullptr;

LONG CALLBACK vectored_handler(EXCEPTION_POINTERS* ep) {
    if (ep == nullptr || ep->ExceptionRecord == nullptr || ep->ContextRecord == nullptr)
        return EXCEPTION_CONTINUE_SEARCH;

    // EXCEPTION_STACK_OVERFLOW is deliberately absent from is_hardware_fault:
    // recovering from it means running the bail stub on the stack that just ran
    // out, which faults again. It passes through and the process dies, which is
    // what would have happened anyway.
    const DWORD code = ep->ExceptionRecord->ExceptionCode;
    if (!is_hardware_fault(code)) return EXCEPTION_CONTINUE_SEARCH;

    std::uintptr_t addr = 0;
    if (ep->ExceptionRecord->NumberParameters >= 2)
        addr = static_cast<std::uintptr_t>(ep->ExceptionRecord->ExceptionInformation[1]);

    const std::uintptr_t resume =
        claim(addr, static_cast<std::uintptr_t>(ep->ContextRecord->Eip), code);
    if (resume == 0) {
        // The fault is not ours to recover, but it is worth a line: under Wine
        // an unhandled fault reaches the AeDebug dialog, which nobody can click
        // headless, and the process then sits there forever looking like a
        // hang. A few words of stack turn that into something readable. Capped
        // so a fault storm cannot fill the disk.
        if (g_passthrough_reports < kMaxPassthroughReports) {
            ++g_passthrough_reports;
            report("passed through", "(not a hook body)", addr,
                   static_cast<std::uintptr_t>(ep->ContextRecord->Eip), code);
            report_stack(static_cast<std::uintptr_t>(ep->ContextRecord->Esp));
        }
        return EXCEPTION_CONTINUE_SEARCH;   // the game's, not ours
    }

    // Hand the thread back to the OS with a different program counter. Letting
    // NtContinue do the resume is the sanctioned path; longjmp-ing from inside
    // the handler would abandon the dispatcher's own frame.
    ep->ContextRecord->Eip = static_cast<DWORD>(resume);
    return EXCEPTION_CONTINUE_EXECUTION;
}

#else

struct sigaction g_old_segv;
struct sigaction g_old_bus;

// Pass a fault we did not cause back to whoever owned the signal before us.
//
// Simply returning is not an option: the kernel would re-execute the faulting
// instruction and we would loop forever. Either the previous handler runs, or
// the disposition goes back to default and the return kills the process the way
// it should have been killed.
void passthrough(int sig, siginfo_t* info, void* uc) {
    const struct sigaction& old = (sig == SIGBUS) ? g_old_bus : g_old_segv;

    if ((old.sa_flags & SA_SIGINFO) != 0 && old.sa_sigaction != nullptr) {
        old.sa_sigaction(sig, info, uc);
        return;
    }
    if (old.sa_handler != SIG_DFL && old.sa_handler != SIG_IGN && old.sa_handler != nullptr) {
        old.sa_handler(sig);
        return;
    }

    // SIG_DFL, or SIG_IGN which cannot be honoured for a synchronous fault.
    struct sigaction dfl {};
    dfl.sa_handler = SIG_DFL;
    sigemptyset(&dfl.sa_mask);
    ::sigaction(sig, &dfl, nullptr);
}

void signal_handler(int sig, siginfo_t* info, void* ucontext) {
    auto* uc = static_cast<ucontext_t*>(ucontext);
    const std::uintptr_t addr =
        info != nullptr ? reinterpret_cast<std::uintptr_t>(info->si_addr) : 0;
    const std::uintptr_t pc =
        uc != nullptr ? static_cast<std::uintptr_t>(uc->uc_mcontext.gregs[REG_EIP]) : 0;

    const std::uintptr_t resume = uc != nullptr
        ? claim(addr, pc, static_cast<unsigned long>(sig))
        : 0;
    if (resume == 0) {
        passthrough(sig, info, ucontext);
        return;
    }

    // sigreturn will restore this context, so rewriting EIP here is the same
    // move as the Windows side: the kernel performs the resume, not us.
    uc->uc_mcontext.gregs[REG_EIP] = static_cast<greg_t>(resume);
}

#endif

}  // namespace

// ------------------------------------------------------------ public API ----

void set_fault_log_path(const char* path) {
    if (path == nullptr) { g_log_path[0] = '\0'; return; }
    std::size_t i = 0;
    for (; path[i] != '\0' && i + 1 < sizeof g_log_path; ++i) g_log_path[i] = path[i];
    g_log_path[i] = '\0';
}

void install_fault_guard() {
    if (g_installed) return;
#if defined(_WIN32)
    // First in the chain. A later-registered handler would only see faults the
    // earlier ones declined, and the point is to see ours before anything else
    // decides what to do about them.
    g_veh = AddVectoredExceptionHandler(1, vectored_handler);
    g_installed = g_veh != nullptr;
#else
    struct sigaction sa {};
    sa.sa_sigaction = signal_handler;
    sa.sa_flags = SA_SIGINFO | SA_NODEFER;
    sigemptyset(&sa.sa_mask);
    const bool a = ::sigaction(SIGSEGV, &sa, &g_old_segv) == 0;
    const bool b = ::sigaction(SIGBUS, &sa, &g_old_bus) == 0;
    g_installed = a && b;
#endif
}

void remove_fault_guard() {
    if (!g_installed) return;
#if defined(_WIN32)
    if (g_veh != nullptr) RemoveVectoredExceptionHandler(g_veh);
    g_veh = nullptr;
#else
    ::sigaction(SIGSEGV, &g_old_segv, nullptr);
    ::sigaction(SIGBUS, &g_old_bus, nullptr);
#endif
    g_installed = false;
}

bool in_hook_body() { return t_frames.depth > 0; }

void enter_hook_body() {
    ThreadFrames& tf = t_frames;
    if (tf.depth < kMaxDepth) {
        tf.sites[tf.depth] = "(unnamed)";
        tf.poisons[tf.depth] = nullptr;
        tf.armed[tf.depth] = false;   // nobody called setjmp for this one
    }
    ++tf.depth;
}

void leave_hook_body() {
    ThreadFrames& tf = t_frames;
    if (tf.depth > 0) --tf.depth;
}

// ----------------------------------------------------------- FaultFrame -----

FaultFrame::FaultFrame(const char* site, std::atomic<bool>* poison)
    : site_(site), poison_(poison), slot_(t_frames.depth) {
    ThreadFrames& tf = t_frames;
    if (slot_ < kMaxDepth) {
        tf.sites[slot_] = site;
        tf.poisons[slot_] = poison;
        // Armed on construction rather than after setjmp: the macro runs setjmp
        // on the very next statement, and there is no code in between that
        // could fault.
        tf.armed[slot_] = true;
    }
    ++tf.depth;
}

FaultFrame::~FaultFrame() {
    ThreadFrames& tf = t_frames;
    if (slot_ < kMaxDepth) tf.armed[slot_] = false;
    if (tf.depth > 0) --tf.depth;
}

void* FaultFrame::buf() {
    ThreadFrames& tf = t_frames;
    // Past the cap the frame is unarmed: claim() refuses to claim at a depth it
    // has no buffer for, so a fault there passes through rather than jumping
    // somewhere arbitrary.
    return slot_ < kMaxDepth ? static_cast<void*>(&tf.bufs[slot_])
                             : static_cast<void*>(&tf.scratch);
}

void FaultFrame::note_fault() {
    // Take this site out of service. It faulted once; the same call with the
    // same inputs will fault again, and a second recovery tells us nothing the
    // first did not.
    if (poison_ != nullptr) poison_->store(true, std::memory_order_release);

    // And take the whole runtime out of service. The longjmp that got us here
    // skipped every destructor between the fault and this frame, so a
    // lua_State unwound mid-pcall is left inconsistent and the next dispatch
    // into it is not trustworthy. Hooks stay installed and forward to the
    // original; the game keeps running without us.
    //
    // `lua reload` puts it back, because a reload rebuilds every state from
    // scratch. The poison above does not lift: that is per site and permanent.
    set_live(false);

    ThreadFrames& tf = t_frames;
    Runtime::instance().log("fault in hook body \"%s\": address 0x%08lx, pc 0x%08lx, code 0x%lx "
                            "-- site poisoned, scripting off until `lua reload`",
                            site_ != nullptr ? site_ : "(unnamed)",
                            static_cast<unsigned long>(tf.fault_addr),
                            static_cast<unsigned long>(tf.fault_pc),
                            static_cast<unsigned long>(tf.fault_code));
}

}  // namespace kp::runtime
