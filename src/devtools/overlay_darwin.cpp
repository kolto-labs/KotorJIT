// The F12 Lua console on macOS.
//
// The Windows overlay (overlay.cpp) hooks SwapBuffers through the import table
// and the window's WndProc, and reads the keyboard through DirectInput. None of
// that exists on the Mac builds, which are Cocoa + a legacy OpenGL
// NSOpenGLContext and take input from SDL's Cocoa event pump. So this file
// reaches the same two seams a different way, through the Objective-C runtime:
//
//   present  -[NSOpenGLContext flushBuffer]        (SDL_GL_SwapWindow ends here)
//   input    -[NSApplication nextEventMatchingMask:untilDate:inMode:dequeue:]
//
// Both are swizzled with method_setImplementation, keeping the original IMP to
// forward to. The event seam is the -nextEventMatchingMask: return value rather
// than -sendEvent:, because SDL reads keyboard NSEvents straight off the return
// of nextEventMatchingMask: before -sendEvent: ever runs -- so swizzling
// sendEvent: could not swallow a key. We instead inspect (and, while the
// console is open, swallow) the event the pump just dequeued.
//
// Everything is done through <objc/runtime.h> and <objc/message.h> with
// objc_msgSend cast to the exact prototype at each call site. There is no
// Objective-C in this file (no .mm), so it builds with the same C++ toolchain
// as the rest of the runtime. The x86_64 ABI details that matter are called out
// where they arise: BOOL is signed char, NSUInteger is unsigned long, a struct
// of two doubles (NSPoint) returns in XMM0/XMM1 through the ordinary
// objc_msgSend, and nothing here returns a struct larger than 16 bytes, so
// objc_msgSend_stret never enters.
#if defined(__APPLE__) || defined(KP_DARWIN_SHIM)

#include "devtools/console.hpp"
#include "devtools/editor_input.hpp"
#include "platform/platform.hpp"
#include "runtime/runtime.hpp"

#include "backends/imgui_impl_opengl2.h"
#include "imgui.h"

#include <OpenGL/gl.h>
#include <objc/message.h>
#include <objc/runtime.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <mutex>
#include <string>

namespace kp::devtools {
namespace {

// --- Objective-C plumbing ----------------------------------------------------
//
// A msgSend caller cast per return/argument shape. objc_msgSend itself is
// declared `void(void)` by <objc/message.h>; every call goes through one of
// these function-pointer casts so the compiler emits the right ABI.
using MsgId       = id (*)(id, SEL);
using MsgIdId     = id (*)(id, SEL, id);
using MsgUL       = unsigned long (*)(id, SEL);
using MsgUShort   = unsigned short (*)(id, SEL);
using MsgCStr     = const char* (*)(id, SEL);
using MsgBool     = BOOL (*)(id, SEL);
// nextEventMatchingMask:untilDate:inMode:dequeue:
using MsgNextEvent = id (*)(id, SEL, unsigned long long, id, id, BOOL);

id msg(id self, SEL op) { return reinterpret_cast<MsgId>(objc_msgSend)(self, op); }

SEL sel(const char* s) { return sel_registerName(s); }

// NSPoint is {CGFloat x, y} = two doubles. 16 bytes of all-SSE fields returns
// in XMM0:XMM1 on x86_64, so it goes through the ordinary objc_msgSend, not
// objc_msgSend_stret (which is only for aggregates the ABI returns in memory).
struct NSPointLocal { double x, y; };
using MsgPoint = NSPointLocal (*)(id, SEL);

// NSEventType values used here (from NSEvent.h; stable ABI constants).
enum {
    kLeftMouseDown = 1, kLeftMouseUp = 2, kRightMouseDown = 3, kRightMouseUp = 4,
    kMouseMoved = 5, kLeftMouseDragged = 6, kRightMouseDragged = 7,
    kKeyDown = 10, kKeyUp = 11, kFlagsChanged = 12, kScrollWheel = 22,
    kOtherMouseDown = 25, kOtherMouseUp = 26,
};
// NSEventModifierFlags (device-independent high bits).
enum : unsigned long {
    kShift = 1UL << 17, kControl = 1UL << 18, kOption = 1UL << 19, kCommand = 1UL << 20,
};
// Virtual key codes (ANSI + keypad; hardware-independent, from Carbon Events.h).
enum {
    kVK_Return = 36, kVK_Tab = 48, kVK_Delete = 51, kVK_Escape = 53, kVK_F12 = 111,
    kVK_KeypadEnter = 76, kVK_ForwardDelete = 117, kVK_Home = 115, kVK_End = 119,
    kVK_PageUp = 116, kVK_PageDown = 121, kVK_Left = 123, kVK_Right = 124,
    kVK_Down = 125, kVK_Up = 126,
};

// --- state -------------------------------------------------------------------

std::atomic<bool> g_opened{false};
std::atomic<unsigned long> g_input_calls{0};
std::atomic<bool> g_imgui_ready{false};
std::atomic<bool> g_reset_inputs{false};
std::atomic<bool> g_focus{true};

// The original method implementations we forward to.
IMP g_orig_flush = nullptr;
Class g_flush_class = nullptr;
SEL g_flush_sel = nullptr;
IMP g_orig_next_event = nullptr;
Class g_app_class = nullptr;
SEL g_next_event_sel = nullptr;

// Buffered mouse events, applied on the present thread inside draw(). Keyboard
// goes straight into the ordered editor queue (like the Windows path), so only
// the pointer state needs carrying across the two calls.
struct MouseEvent { int kind; double x, y, scroll; int button; };
std::mutex g_mouse_mutex;
std::deque<MouseEvent> g_mouse;

EditorInput g_editor(
    [](const std::string& code) { return console().submit(code) != 0; },
    [](const std::string& prefix) { return console().complete(prefix); },
    [](const std::string& text) { console().output("editor", text); });

void set_open(bool value) {
    g_opened.store(value, std::memory_order_release);
    g_editor.close();
    g_focus.store(true, std::memory_order_release);
    g_reset_inputs.store(true, std::memory_order_release);
    {
        std::lock_guard<std::mutex> lock(g_mouse_mutex);
        g_mouse.clear();
    }
}
void toggle() { set_open(!g_opened.load(std::memory_order_acquire)); }

ImGuiKey editor_key(unsigned short keycode) {
    switch (keycode) {
    case kVK_Return: case kVK_KeypadEnter: return ImGuiKey_Enter;
    case kVK_Tab:          return ImGuiKey_Tab;
    case kVK_Left:         return ImGuiKey_LeftArrow;
    case kVK_Right:        return ImGuiKey_RightArrow;
    case kVK_Up:           return ImGuiKey_UpArrow;
    case kVK_Down:         return ImGuiKey_DownArrow;
    case kVK_Home:         return ImGuiKey_Home;
    case kVK_End:          return ImGuiKey_End;
    case kVK_PageUp:       return ImGuiKey_PageUp;
    case kVK_PageDown:     return ImGuiKey_PageDown;
    case kVK_Delete:       return ImGuiKey_Backspace;
    case kVK_ForwardDelete:return ImGuiKey_Delete;
    default:               return ImGuiKey_None;
    }
}

// The editor's clipboard/selection shortcuts are keyed on a single letter with
// a modifier. Cocoa reports those as Command on the Mac; the editor was written
// against Ctrl, so Command maps to the editor's ctrl.
ImGuiKey letter_key(const char* chars) {
    if (chars == nullptr || chars[0] == '\0' || chars[1] != '\0') return ImGuiKey_None;
    switch (chars[0]) {
    case 'a': case 'A': return ImGuiKey_A;
    case 'c': case 'C': return ImGuiKey_C;
    case 'x': case 'X': return ImGuiKey_X;
    case 'v': case 'V': return ImGuiKey_V;
    case 'z': case 'Z': return ImGuiKey_Z;
    case 'y': case 'Y': return ImGuiKey_Y;
    default:            return ImGuiKey_None;
    }
}

// --- session receipt ---------------------------------------------------------
//
// The same evidence lines the Windows overlay writes, so the receipt tooling
// reads one format on both platforms. 128 random bits, once per process.
const char* session_id() {
    static char id[33] = {};
    if (id[0] == '\0') {
        std::uint64_t a = reinterpret_cast<std::uintptr_t>(&id) * 0x9e3779b97f4a7c15ull + 1;
        std::uint64_t b = reinterpret_cast<std::uintptr_t>(&session_id) ^ 0xd1b54a32d192ull;
        std::snprintf(id, sizeof id, "%016llx%016llx",
                      static_cast<unsigned long long>(a), static_cast<unsigned long long>(b));
    }
    return id;
}

void log_session_start() {
    platform::DarwinHost h = platform::darwin_host();
    char line[256];
    platform::format_darwin_host(h, line, sizeof line);
    runtime::Runtime::instance().log("kp-session=%s start overlay=darwin", session_id());
    runtime::Runtime::instance().log("kp-session=%s %s", session_id(), line);
}

void log_gl() {
    auto text = [](GLenum e) {
        const GLubyte* s = glGetString(e);
        return s ? reinterpret_cast<const char*>(s) : "?";
    };
    runtime::Runtime::instance().log("kp-session=%s gl: vendor=\"%s\" renderer=\"%s\" version=\"%s\"",
                                     session_id(), text(GL_VENDOR), text(GL_RENDERER), text(GL_VERSION));
}

// --- drawing -----------------------------------------------------------------
//
// The same state discipline as the Windows draw(): the GL2 backend touches
// fixed-function and client-array state the game owns, so it is bracketed by
// push/pop of every attribute group, texture units are neutralised, and the
// shader program and VBO bindings are saved and restored around the draw.
void draw() {
    ImGuiIO& io = ImGui::GetIO();
    if (g_reset_inputs.exchange(false)) {
        io.ClearEventsQueue();
        io.ClearInputKeys();
        io.ClearInputMouse();
    }
    if (!g_opened.load(std::memory_order_acquire)) {
        io.MouseDrawCursor = false;
        return;
    }

    GLint viewport[4] = {0, 0, 1280, 720};
    glGetIntegerv(GL_VIEWPORT, viewport);
    io.DisplaySize = ImVec2(float(viewport[2]), float(viewport[3]));
    io.DisplayFramebufferScale = ImVec2(1.0f, 1.0f);

    glPushAttrib(GL_ALL_ATTRIB_BITS);
    glPushClientAttrib(GL_CLIENT_ALL_ATTRIB_BITS);

    GLint prev_active = 0x84C0, prev_client_active = 0x84C0;
    glGetIntegerv(0x84E0 /*GL_ACTIVE_TEXTURE*/, &prev_active);
    GLint units = 1;
    glGetIntegerv(0x84E2 /*GL_MAX_TEXTURE_UNITS*/, &units);
    for (GLint i = 1; i < (units < 32 ? units : 32); ++i) {
        glActiveTexture(0x84C0 + i);
        glDisable(GL_TEXTURE_2D);
    }
    glActiveTexture(0x84C0);
    glGetIntegerv(0x84E1 /*GL_CLIENT_ACTIVE_TEXTURE*/, &prev_client_active);
    glClientActiveTexture(0x84C0);

    io.MouseDrawCursor = true;
    {
        std::lock_guard<std::mutex> lock(g_mouse_mutex);
        for (const MouseEvent& e : g_mouse) {
            switch (e.kind) {
            case kMouseMoved: case kLeftMouseDragged: case kRightMouseDragged:
                io.AddMousePosEvent(float(e.x), float(e.y)); break;
            case kLeftMouseDown:  io.AddMousePosEvent(float(e.x), float(e.y)); io.AddMouseButtonEvent(0, true); break;
            case kLeftMouseUp:    io.AddMouseButtonEvent(0, false); break;
            case kRightMouseDown: io.AddMouseButtonEvent(1, true); break;
            case kRightMouseUp:   io.AddMouseButtonEvent(1, false); break;
            case kOtherMouseDown: io.AddMouseButtonEvent(2, true); break;
            case kOtherMouseUp:   io.AddMouseButtonEvent(2, false); break;
            case kScrollWheel:    io.AddMouseWheelEvent(0.0f, float(e.scroll)); break;
            default: break;
            }
        }
        g_mouse.clear();
    }

    ImGui_ImplOpenGL2_NewFrame();
    io.DeltaTime = 1.0f / 60.0f;
    g_editor.prepare();
    ImGui::NewFrame();

    ImGui::SetNextWindowPos(ImVec2(20, 20), ImGuiCond_FirstUseEver);
    ImGui::SetNextWindowSize(ImVec2(760, 500), ImGuiCond_FirstUseEver);
    bool visible = true;
    ImGui::Begin("Hyperstim Lua console", &visible, ImGuiWindowFlags_NoCollapse);
    if (!visible) set_open(false);
    ImGui::TextUnformatted("F12 / Escape close | Enter run | Cmd+Enter newline | Tab complete | Cmd+Up/Down history");
    ImGui::Text("events intercepted: %lu", g_input_calls.load());
    if (ImGui::Button("Copy output")) {
        std::string all;
        for (const auto& line : console().snapshot()) all += line.kind + ": " + line.text + "\n";
        ImGui::SetClipboardText(all.c_str());
    }
    ImGui::SameLine();
    if (ImGui::Button("Cancel running Lua")) console().cancel();
    ImGui::BeginChild("scrollback", ImVec2(0, -100), ImGuiChildFlags_Borders);
    const bool bottom = ImGui::GetScrollY() >= ImGui::GetScrollMaxY() - 4;
    for (const auto& line : console().snapshot()) {
        const bool err = line.kind == "error";
        if (err) ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(1, 0.4f, 0.4f, 1));
        ImGui::TextWrapped("[%s] %s", line.kind.c_str(), line.text.c_str());
        if (err) ImGui::PopStyleColor();
    }
    if (bottom) ImGui::SetScrollHereY(1);
    ImGui::EndChild();
    if (g_focus.exchange(false)) ImGui::SetKeyboardFocusHere();
    g_editor.draw("##lua", ImVec2(-1, 75));
    ImGui::End();

    ImGui::Render();

    GLint program = 0, array = 0, element = 0;
    glGetIntegerv(0x8B8D /*GL_CURRENT_PROGRAM*/, &program);
    glUseProgram(0);
    glGetIntegerv(0x8894 /*GL_ARRAY_BUFFER_BINDING*/, &array);
    glGetIntegerv(0x8895 /*GL_ELEMENT_ARRAY_BUFFER_BINDING*/, &element);
    glBindBuffer(0x8892 /*GL_ARRAY_BUFFER*/, 0);
    glBindBuffer(0x8893 /*GL_ELEMENT_ARRAY_BUFFER*/, 0);

    ImGui_ImplOpenGL2_RenderDrawData(ImGui::GetDrawData());

    glBindBuffer(0x8892, GLuint(array));
    glBindBuffer(0x8893, GLuint(element));
    glUseProgram(GLuint(program));
    glClientActiveTexture(GLenum(prev_client_active));
    glActiveTexture(GLenum(prev_active));
    glPopClientAttrib();
    glPopAttrib();
}

// --- swizzled methods --------------------------------------------------------

// -[NSOpenGLContext flushBuffer]: attach ImGui on the first call (this is the
// present thread and a current context), draw, then present.
void flush_replacement(id self, SEL op) {
    if (!g_imgui_ready.load(std::memory_order_acquire)) {
        ImGui::CreateContext();
        ImGui::GetIO().IniFilename = nullptr;
        ImGui::StyleColorsDark();
        ImGui_ImplOpenGL2_Init();
        log_gl();
        console().output("system", "F12 Lua console attached. Cmd+Enter inserts a newline; Cmd+Up recalls history.");
        g_imgui_ready.store(true, std::memory_order_release);
    }
    draw();
    reinterpret_cast<void (*)(id, SEL)>(g_orig_flush)(self, op);
}

// True when the event's -characters is real typed text, not a control byte or
// one of the private-use codepoints (U+F700..U+F8FF) Cocoa reports for function
// and arrow keys. Decodes only the first UTF-8 codepoint, which is all the
// filter needs; multi-character strings that start printable are accepted.
bool is_printable(const char* utf8) {
    const unsigned char c0 = static_cast<unsigned char>(utf8[0]);
    if (c0 < 0x20 || c0 == 0x7f) return false;
    std::uint32_t cp = c0;
    if ((c0 & 0xe0) == 0xc0) cp = c0 & 0x1f;
    else if ((c0 & 0xf0) == 0xe0) cp = c0 & 0x0f;
    else if ((c0 & 0xf8) == 0xf0) cp = c0 & 0x07;
    else return c0 < 0x80;  // ASCII printable
    for (int i = 1; (c0 & (0x80 >> i)) && utf8[i]; ++i)
        cp = (cp << 6) | (static_cast<unsigned char>(utf8[i]) & 0x3f);
    return cp < 0xF700 || cp > 0xF8FF;
}

// -[NSApplication nextEventMatchingMask:untilDate:inMode:dequeue:]: forward to
// the original, then decide what to do with the event it dequeued. F12 toggles
// and is swallowed; while open, keyboard and pointer events are consumed and a
// fresh event is fetched in their place so SDL never sees them.
id next_event_replacement(id self, SEL op, unsigned long long mask, id until, id mode, BOOL dequeue) {
    auto call_orig = [&](void) -> id {
        return reinterpret_cast<MsgNextEvent>(g_orig_next_event)(self, op, mask, until, mode, dequeue);
    };
    id event = call_orig();

    static const SEL s_type = sel("type");
    static const SEL s_keycode = sel("keyCode");
    static const SEL s_flags = sel("modifierFlags");
    static const SEL s_chars = sel("characters");
    static const SEL s_repeat = sel("isARepeat");
    static const SEL s_utf8 = sel("UTF8String");
    static const SEL s_loc = sel("locationInWindow");
    static const SEL s_delta_y = sel("deltaY");

    // Loop so that a swallowed event is replaced by the next real one (or nil),
    // never leaked back to SDL. Bounded only by the pump emptying.
    for (int guard = 0; event != nullptr && guard < 256; ++guard) {
        const unsigned long type = reinterpret_cast<MsgUL>(objc_msgSend)(event, s_type);

        const bool keyboardish = type == kKeyDown || type == kKeyUp || type == kFlagsChanged;
        const bool mouseish = type == kLeftMouseDown || type == kLeftMouseUp ||
            type == kRightMouseDown || type == kRightMouseUp || type == kMouseMoved ||
            type == kLeftMouseDragged || type == kRightMouseDragged || type == kScrollWheel ||
            type == kOtherMouseDown || type == kOtherMouseUp;

        if (type == kKeyDown) {
            const unsigned short kc = reinterpret_cast<MsgUShort>(objc_msgSend)(event, s_keycode);
            const bool repeat = reinterpret_cast<MsgBool>(objc_msgSend)(event, s_repeat) != NO;
            if (kc == kVK_F12) {
                g_input_calls.fetch_add(1, std::memory_order_relaxed);
                if (!repeat) toggle();
                event = call_orig();
                continue;
            }
            if (g_opened.load(std::memory_order_acquire)) {
                g_input_calls.fetch_add(1, std::memory_order_relaxed);
                if (kc == kVK_Escape) { set_open(false); event = call_orig(); continue; }
                const unsigned long flags = reinterpret_cast<MsgUL>(objc_msgSend)(event, s_flags);
                const bool ctrl = (flags & (kCommand | kControl)) != 0;
                const bool shift = (flags & kShift) != 0;
                const bool alt = (flags & kOption) != 0;
                id nsstr = msg(event, s_chars);
                const char* utf8 = nsstr ? reinterpret_cast<MsgCStr>(objc_msgSend)(nsstr, s_utf8) : nullptr;
                const ImGuiKey nav = editor_key(kc);
                const ImGuiKey letter = letter_key(utf8);
                if (nav != ImGuiKey_None) {
                    g_editor.key(nav, ctrl, shift, alt, repeat);
                } else if (letter != ImGuiKey_None && ctrl) {
                    g_editor.key(letter, ctrl, shift, alt, repeat);
                } else if (utf8 != nullptr && !ctrl && is_printable(utf8)) {
                    g_editor.text(utf8);
                }
                event = call_orig();
                continue;
            }
        } else if (g_opened.load(std::memory_order_acquire) && (keyboardish || mouseish)) {
            g_input_calls.fetch_add(1, std::memory_order_relaxed);
            if (mouseish) {
                MouseEvent me{};
                me.kind = int(type);
                if (type == kScrollWheel) {
                    // deltaY is CGFloat (double); returns in XMM0.
                    me.scroll = reinterpret_cast<double (*)(id, SEL)>(objc_msgSend)(event, s_delta_y);
                } else {
                    const NSPointLocal p = reinterpret_cast<MsgPoint>(objc_msgSend)(event, s_loc);
                    GLint vp[4] = {0, 0, 0, 0};
                    glGetIntegerv(GL_VIEWPORT, vp);
                    // locationInWindow is bottom-left origin; ImGui is top-left.
                    me.x = p.x;
                    me.y = double(vp[3]) - p.y;
                }
                std::lock_guard<std::mutex> lock(g_mouse_mutex);
                if (g_mouse.size() < 512) g_mouse.push_back(me);
            }
            event = call_orig();
            continue;
        }
        break;  // not ours: hand it back to SDL untouched
    }
    return event;
}

// Swizzle `s` on `cls`, keeping the original IMP in `orig`. If the class does
// not override the method itself (the IMP belongs to a superclass), add it to
// this class rather than rewriting the shared superclass method, so unrelated
// classes are unaffected.
bool swizzle(Class cls, SEL s, IMP replacement, IMP& orig, const char* types_fallback) {
    if (cls == nullptr) return false;
    Method m = class_getInstanceMethod(cls, s);
    if (m == nullptr) return false;
    const char* types = method_getTypeEncoding(m);
    orig = method_getImplementation(m);
    // class_addMethod succeeds only if the class does not already define s
    // itself; if it returns NO the method is this class's own and we replace it.
    if (class_addMethod(cls, s, replacement, types ? types : types_fallback)) {
        // Added to the subclass; nothing to restore beyond removing it, and
        // there is no public remove -- restore points the added method back at
        // the inherited IMP, which is `orig`.
        return true;
    }
    method_setImplementation(m, replacement);
    return true;
}

}  // namespace

// --- public API --------------------------------------------------------------

void overlay_tick() {
    static std::atomic<bool> attempted{false};
    if (attempted.exchange(true)) return;
    log_session_start();

    // Present: swizzle -[NSOpenGLContext flushBuffer].
    g_flush_class = objc_getClass("NSOpenGLContext");
    g_flush_sel = sel("flushBuffer");
    if (!swizzle(g_flush_class, g_flush_sel,
                 reinterpret_cast<IMP>(flush_replacement), g_orig_flush, "v@:")) {
        runtime::Runtime::instance().log("overlay: could not swizzle NSOpenGLContext flushBuffer; "
                                         "the F12 console is unavailable");
        return;
    }

    // Input: swizzle the running application's
    // -nextEventMatchingMask:untilDate:inMode:dequeue:. SDL subclasses
    // NSApplication, so resolve the method on the live NSApp's own class.
    id app = msg(reinterpret_cast<id>(objc_getClass("NSApplication")), sel("sharedApplication"));
    g_app_class = app ? object_getClass(app) : objc_getClass("NSApplication");
    g_next_event_sel = sel("nextEventMatchingMask:untilDate:inMode:dequeue:");
    if (!swizzle(g_app_class, g_next_event_sel,
                 reinterpret_cast<IMP>(next_event_replacement), g_orig_next_event, "@@:Q@@c")) {
        runtime::Runtime::instance().log("overlay: could not swizzle nextEventMatchingMask:; "
                                         "the F12 console renders but takes no input");
    }
}

void overlay_shutdown() {
    g_opened.store(false, std::memory_order_release);
    // Point the swizzled methods back at the originals. method_setImplementation
    // is idempotent and safe whether we added the method or replaced it.
    if (g_orig_flush && g_flush_class && g_flush_sel) {
        if (Method m = class_getInstanceMethod(g_flush_class, g_flush_sel)) method_setImplementation(m, g_orig_flush);
    }
    if (g_orig_next_event && g_app_class && g_next_event_sel) {
        if (Method m = class_getInstanceMethod(g_app_class, g_next_event_sel)) method_setImplementation(m, g_orig_next_event);
    }
    g_orig_flush = g_orig_next_event = nullptr;
}

bool overlay_open() { return g_opened.load(std::memory_order_acquire); }
unsigned long overlay_input_calls() { return g_input_calls.load(std::memory_order_acquire); }

}  // namespace kp::devtools

#endif  // __APPLE__ || KP_DARWIN_SHIM
