#include "devtools/console.hpp"
#if defined(_WIN32)
#define WIN32_LEAN_AND_MEAN
#define DIRECTINPUT_VERSION 0x0800
#include "backends/imgui_impl_opengl2.h"
#include "backends/imgui_impl_win32.h"
#include "imgui.h"
#include <GL/gl.h>
#include <algorithm>
#include <array>
#include <cctype>
#include <cstdio>
#include <cstring>
#include <deque>
#include <dinput.h>
#include <map>
#include <set>
#include <windows.h>
extern IMGUI_IMPL_API LRESULT ImGui_ImplWin32_WndProcHandler(HWND, UINT, WPARAM,
                                                             LPARAM);
namespace kp::devtools {
namespace {
std::atomic<bool> opened{false};
std::atomic<unsigned long> input_calls{0};
HWND window = nullptr;
WNDPROC previous = nullptr;
HGLRC context = nullptr;
DWORD owner = 0;
using Swap = BOOL(WINAPI *)(HDC);
Swap swap_original = nullptr;
using Cursor = BOOL(WINAPI *)(int, int);
Cursor cursor_original = nullptr;
BOOL WINAPI cursor(int x, int y) {
  return opened ? TRUE : cursor_original(x, y);
}
struct Patch {
  void **slot;
  void *old;
  void *ours;
};
std::vector<Patch> patches;
struct Input {
  UINT msg;
  WPARAM w;
  LPARAM l;
  bool ctrl, shift, alt, super;
};
std::mutex input_mutex;
std::deque<Input> inputs;
std::array<char, 16385> edit{};
std::vector<std::string> history;
int history_pos = -1;
std::atomic<bool> focus{true};
std::atomic<bool> reset_inputs{false};
using State = HRESULT(WINAPI *)(IDirectInputDevice8A *, DWORD, LPVOID);
using Data = HRESULT(WINAPI *)(IDirectInputDevice8A *, DWORD,
                               LPDIDEVICEOBJECTDATA, LPDWORD, DWORD);
struct DeviceHooks {
  void **vtable;
  State state;
  Data data;
};
std::atomic<bool> release_keyboard{false};
std::atomic<unsigned> input_epoch{0};
struct BufferedDevice {
  unsigned epoch = 0;
  std::set<DWORD> pressed;
};
std::mutex buffered_mutex;
std::map<IDirectInputDevice8A *, BufferedDevice> buffered_devices;
std::vector<DeviceHooks> devices;
IDirectInput8A *directinput = nullptr;
std::vector<IDirectInputDevice8A *> probes;
bool patch(void **slot, void *replacement) {
  for (auto &p : patches)
    if (p.slot == slot)
      return true;
  DWORD old;
  if (!VirtualProtect(slot, sizeof(void *), PAGE_READWRITE, &old))
    return false;
  void *prior = InterlockedExchangePointer(
      reinterpret_cast<void *volatile *>(slot), replacement);
  DWORD ignored;
  VirtualProtect(slot, sizeof(void *), old, &ignored);
  patches.push_back({slot, prior, replacement});
  return true;
}
HRESULT WINAPI get_state(IDirectInputDevice8A *self, DWORD size, LPVOID data) {
  auto **v = *reinterpret_cast<void ***>(self);
  State orig = nullptr;
  for (auto &h : devices)
    if (h.vtable == v)
      orig = h.state;
  if (!orig)
    return DIERR_GENERIC;
  HRESULT r = orig(self, size, data);
  input_calls++;
  if (SUCCEEDED(r) && data) {
    bool suppress = opened;
    if (size == 256) {
      auto *keys = static_cast<unsigned char *>(data);
      keys[DIK_F12] = 0;
      if (release_keyboard) {
        bool held = false;
        for (unsigned i = 0; i < 256; ++i)
          held = held || keys[i] != 0;
        if (!held)
          release_keyboard = false;
        suppress = true;
      }
    }
    if (suppress)
      std::memset(data, 0, size);
  }
  return r;
}
HRESULT WINAPI get_data(IDirectInputDevice8A *self, DWORD size,
                        LPDIDEVICEOBJECTDATA data, LPDWORD count, DWORD flags) {
  auto **v = *reinterpret_cast<void ***>(self);
  Data orig = nullptr;
  for (auto &h : devices)
    if (h.vtable == v)
      orig = h.data;
  if (!orig)
    return DIERR_GENERIC;
  const DWORD capacity = count ? *count : 0;
  HRESULT r = orig(self, size, data, count, flags);
  input_calls++;
  if (count && SUCCEEDED(r)) {
    std::lock_guard lock(buffered_mutex);
    auto &state = buffered_devices[self];
    const unsigned epoch = input_epoch;
    if (opened || state.epoch != epoch) {
      DWORD discarded = INFINITE;
      orig(self, size, nullptr, &discarded, 0);
      *count = 0;
      // Buffered input consumers retain their last key state. Sending no
      // records alone would keep a key pressed before F12 latched forever.
      if (data && size >= sizeof(DIDEVICEOBJECTDATA_DX3)) {
        while (!state.pressed.empty() && *count < capacity) {
          DIDEVICEOBJECTDATA release{};
          release.dwOfs = *state.pressed.begin();
          release.dwTimeStamp = GetTickCount();
          std::memcpy(reinterpret_cast<unsigned char *>(data) + size * (*count),
                      &release, std::min(size, DWORD(sizeof release)));
          ++*count;
          state.pressed.erase(state.pressed.begin());
        }
      }
      if (state.pressed.empty())
        state.epoch = epoch;
    } else if (data && !(flags & DIGDD_PEEK)) {
      for (DWORD i = 0; i < *count; ++i) {
        DIDEVICEOBJECTDATA event{};
        std::memcpy(&event, reinterpret_cast<unsigned char *>(data) + size * i,
                    std::min(size, DWORD(sizeof event)));
        if (event.dwData & 0x80) {
          if (state.pressed.size() < 256)
            state.pressed.insert(event.dwOfs);
        } else
          state.pressed.erase(event.dwOfs);
      }
    }
  }
  return r;
}
void attach_input() {
  // Probe devices share implementation vtables with already-created devices.
  // This also covers late runtime attachment; it does not depend on seeing
  // the game's earlier DirectInput8Create call.
  if (FAILED(DirectInput8Create(
          GetModuleHandle(nullptr), DIRECTINPUT_VERSION, IID_IDirectInput8A,
          reinterpret_cast<void **>(&directinput), nullptr)))
    return;
  for (const GUID *guid : {&GUID_SysKeyboard, &GUID_SysMouse}) {
    IDirectInputDevice8A *d = nullptr;
    if (FAILED(directinput->CreateDevice(*guid, &d, nullptr)))
      continue;
    probes.push_back(d);
    auto **v = *reinterpret_cast<void ***>(d);
    bool known = false;
    for (auto &h : devices)
      if (h.vtable == v)
        known = true;
    if (known)
      continue;
    devices.push_back(
        {v, reinterpret_cast<State>(v[9]), reinterpret_cast<Data>(v[10])});
    patch(v + 9, reinterpret_cast<void *>(&get_state));
    patch(v + 10, reinterpret_cast<void *>(&get_data));
  }
}
void set_open(bool value) {
  if (opened.load() != value)
    ++input_epoch;
  opened = value;
  release_keyboard = true;
  focus = true;
  if (context && owner == GetCurrentThreadId()) {
    ImGui::GetIO().ClearInputKeys();
    ImGui::GetIO().ClearInputMouse();
    reset_inputs = false;
  } else
    reset_inputs = true;
}
void toggle() { set_open(!opened.load()); }
LRESULT CALLBACK wndproc(HWND h, UINT msg, WPARAM w, LPARAM l) {
  if (msg == WM_KILLFOCUS)
    set_open(false);
  if (msg == WM_KEYDOWN && w == VK_F12) {
    if (!(l & (1L << 30)))
      toggle();
    return 0;
  }
  if (msg == WM_KEYUP && w == VK_F12)
    return 0;
  if (opened && msg == WM_KEYDOWN && w == VK_ESCAPE) {
    set_open(false);
    return 0;
  }
  if (opened) {
    if (owner == GetCurrentThreadId()) {
      // The backend samples GetKeyState; dispatch on this owning thread at
      // message time so fast Ctrl+A/paste/history chords keep their modifiers.
      ImGui_ImplWin32_WndProcHandler(h, msg, w, l);
    } else {
      std::lock_guard lock(input_mutex);
      if (inputs.size() < 1024)
        inputs.push_back({msg, w, l, (GetKeyState(VK_CONTROL) & 0x8000) != 0,
                          (GetKeyState(VK_SHIFT) & 0x8000) != 0,
                          (GetKeyState(VK_MENU) & 0x8000) != 0,
                          (GetKeyState(VK_LWIN) & 0x8000) != 0 ||
                              (GetKeyState(VK_RWIN) & 0x8000) != 0});
    }
    if ((msg >= WM_KEYFIRST && msg <= WM_KEYLAST) ||
        (msg >= WM_MOUSEFIRST && msg <= WM_MOUSELAST) || msg == WM_INPUT)
      return 0;
    if (msg == WM_SETCURSOR) {
      SetCursor(LoadCursor(nullptr, IDC_ARROW));
      return TRUE;
    }
  }
  return CallWindowProc(previous, h, msg, w, l);
}
int edit_callback(ImGuiInputTextCallbackData *data) {
  if (data->EventFlag == ImGuiInputTextFlags_CallbackAlways &&
      ImGui::GetIO().KeyCtrl &&
      (ImGui::IsKeyPressed(ImGuiKey_UpArrow) ||
       ImGui::IsKeyPressed(ImGuiKey_DownArrow))) {
    if (history.empty())
      return 0;
    if (ImGui::IsKeyPressed(ImGuiKey_UpArrow))
      history_pos = history_pos < 0 ? int(history.size()) - 1
                                    : std::max(0, history_pos - 1);
    else if (history_pos >= 0)
      history_pos++;
    if (history_pos >= int(history.size()))
      history_pos = -1;
    data->DeleteChars(0, data->BufTextLen);
    if (history_pos >= 0)
      data->InsertChars(0, history[history_pos].c_str());
  } else if (data->EventFlag == ImGuiInputTextFlags_CallbackCompletion) {
    int start = data->CursorPos;
    while (start > 0 &&
           (std::isalnum(static_cast<unsigned char>(data->Buf[start - 1])) ||
            data->Buf[start - 1] == '_' || data->Buf[start - 1] == '.'))
      --start;
    auto matches = console().complete(
        std::string(data->Buf + start, data->CursorPos - start));
    if (matches.size() == 1) {
      data->DeleteChars(start, data->CursorPos - start);
      data->InsertChars(start, matches[0].c_str());
    } else
      for (auto &s : matches)
        console().output("completion", s);
  }
  return 0;
}
template <class Function> Function gl_proc(const char *name) {
  PROC address = wglGetProcAddress(name);
  auto numeric = reinterpret_cast<std::uintptr_t>(address);
  if (numeric <= 3 || numeric == ~std::uintptr_t(0))
    return nullptr;
  Function result;
  static_assert(sizeof(result) == sizeof(address));
  std::memcpy(&result, &address, sizeof(result));
  return result;
}
void draw() {
  // The upstream GL2 backend does not preserve client arrays or pixel-store
  // state. The game owns both, including VBO-backed array pointers.
  glPushAttrib(GL_ALL_ATTRIB_BITS);
  glPushClientAttrib(GL_CLIENT_ALL_ATTRIB_BITS);
  using ActiveTexture = void(APIENTRY *)(GLenum);
  auto active = gl_proc<ActiveTexture>("glActiveTexture");
  auto client_active = gl_proc<ActiveTexture>("glClientActiveTexture");
  GLint previous_active = 0x84C0, previous_client_active = 0x84C0;
  if (active) {
    glGetIntegerv(0x84E0, &previous_active);
    GLint units = 1;
    glGetIntegerv(0x84E2, &units);
    for (GLint i = 1; i < std::min(units, 32); ++i) {
      active(0x84C0 + i);
      glDisable(GL_TEXTURE_2D);
    }
    active(0x84C0);
  }
  if (client_active) {
    glGetIntegerv(0x84E1, &previous_client_active);
    client_active(0x84C0);
  }
  auto &io = ImGui::GetIO();
  if (reset_inputs.exchange(false)) {
    io.ClearInputKeys();
    io.ClearInputMouse();
  }
  io.MouseDrawCursor = opened;
  {
    std::lock_guard lock(input_mutex);
    for (auto &e : inputs) {
      ImGui_ImplWin32_WndProcHandler(window, e.msg, e.w, e.l);
      io.AddKeyEvent(ImGuiMod_Ctrl, e.ctrl);
      io.AddKeyEvent(ImGuiMod_Shift, e.shift);
      io.AddKeyEvent(ImGuiMod_Alt, e.alt);
      io.AddKeyEvent(ImGuiMod_Super, e.super);
    }
    inputs.clear();
  }
  ImGui_ImplOpenGL2_NewFrame();
  ImGui_ImplWin32_NewFrame();
  ImGui::NewFrame();
  if (opened) {
    ImGui::SetNextWindowPos({20, 20}, ImGuiCond_FirstUseEver);
    ImGui::SetNextWindowSize({760, 500}, ImGuiCond_FirstUseEver);
    bool visible = true;
    ImGui::Begin("KotorPhasor Lua console", &visible,
                 ImGuiWindowFlags_NoCollapse);
    if (!visible)
      set_open(false);
    ImGui::TextUnformatted("F12 / Escape close | Enter run | Ctrl+Enter "
                           "newline | Tab complete | Ctrl+Up/Down history");
    ImGui::Text("DirectInput calls: %lu", input_calls.load());
    if (ImGui::Button("Copy output")) {
      std::string all;
      for (auto &line : console().snapshot())
        all += line.kind + ": " + line.text + "\n";
      ImGui::SetClipboardText(all.c_str());
    }
    ImGui::SameLine();
    if (ImGui::Button("Cancel running Lua"))
      console().cancel();
    ImGui::BeginChild("scrollback", {0, -100}, ImGuiChildFlags_Borders);
    bool bottom = ImGui::GetScrollY() >= ImGui::GetScrollMaxY() - 4;
    for (auto &line : console().snapshot()) {
      if (line.kind == "error")
        ImGui::PushStyleColor(ImGuiCol_Text, {1, .4f, .4f, 1});
      ImGui::TextWrapped("[%s] %s", line.kind.c_str(), line.text.c_str());
      if (line.kind == "error")
        ImGui::PopStyleColor();
    }
    if (bottom)
      ImGui::SetScrollHereY(1);
    ImGui::EndChild();
    if (focus.exchange(false)) {
      ImGui::SetKeyboardFocusHere();
      focus = false;
    }
    // Multiline EnterReturnsTrue uses Ctrl+Enter by default; invert via
    // CtrlEnterForNewLine so plain Enter submits and modified Enter inserts.
    io.ConfigInputTextEnterKeepActive = true;
    bool submit =
        ImGui::InputTextMultiline("##lua", edit.data(), edit.size(), {-1, 75},
                                  ImGuiInputTextFlags_EnterReturnsTrue |
                                      ImGuiInputTextFlags_CtrlEnterForNewLine |
                                      ImGuiInputTextFlags_CallbackCompletion |
                                      ImGuiInputTextFlags_CallbackAlways,
                                  edit_callback);
    if (submit && edit[0]) {
      std::string s = edit.data();
      if (console().submit(s)) {
        history.push_back(s);
        if (history.size() > 100)
          history.erase(history.begin());
        edit[0] = 0;
        history_pos = -1;
      }
      focus = true;
    }
    ImGui::End();
  }
  ImGui::Render();
  // GL2 backend saves fixed-function state; shaders and VBOs need explicit
  // preservation on compatibility contexts that also use modern GL features.
  using UseProgram = void(APIENTRY *)(GLuint);
  using BindBuffer = void(APIENTRY *)(GLenum, GLuint);
  auto use = gl_proc<UseProgram>("glUseProgram");
  auto bind = gl_proc<BindBuffer>("glBindBuffer");
  GLint program = 0, array = 0, element = 0;
  if (use) {
    glGetIntegerv(0x8B8D, &program);
    use(0);
  }
  if (bind) {
    glGetIntegerv(0x8894, &array);
    glGetIntegerv(0x8895, &element);
    bind(0x8892, 0);
    bind(0x8893, 0);
  }
  ImGui_ImplOpenGL2_RenderDrawData(ImGui::GetDrawData());
  if (bind) {
    bind(0x8892, array);
    bind(0x8893, element);
  }
  if (use)
    use(program);
  glPopClientAttrib();
  glPopAttrib();
  if (client_active)
    client_active(previous_client_active);
  if (active)
    active(previous_active);
}
BOOL WINAPI swap(HDC dc) {
  static thread_local bool inside = false;
  if (!inside && wglGetCurrentContext()) {
    inside = true;
    HWND h = WindowFromDC(dc);
    if (h && (!window || h == window)) {
      if (!context) {
        window = h;
        owner = GetCurrentThreadId();
        context = wglGetCurrentContext();
        ImGui::CreateContext();
        ImGui::GetIO().IniFilename = nullptr;
        ImGui::StyleColorsDark();
        ImGui_ImplWin32_Init(window);
        ImGui_ImplOpenGL2_Init();
        previous = reinterpret_cast<WNDPROC>(SetWindowLongPtr(
            window, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(wndproc)));
        console().output("system",
                         "F12 Lua console attached. Ctrl+Enter inserts a "
                         "newline; Ctrl+Up recalls history.");
      }
      if (owner == GetCurrentThreadId() && context == wglGetCurrentContext())
        draw();
      else if (opened) {
        set_open(false);
        console().output("error", "Render context changed; console closed to "
                                  "restore game input. Restart to reattach.");
      }
    }
    inside = false;
  }
  return swap_original(dc);
}
} // namespace
bool overlay_open() { return opened; }
unsigned long overlay_input_calls() { return input_calls; }
void overlay_tick() {
  static bool attempted = false;
  if (attempted)
    return;
  attempted = true;
  attach_input();
  auto *base = reinterpret_cast<unsigned char *>(GetModuleHandle(nullptr));
  auto *dos = reinterpret_cast<IMAGE_DOS_HEADER *>(base);
  auto *nt = reinterpret_cast<IMAGE_NT_HEADERS *>(base + dos->e_lfanew);
  auto rva = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT]
                 .VirtualAddress;
  if (!rva)
    return;
  for (auto *desc = reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR *>(base + rva);
       desc->Name; ++desc) {
    if (!desc->OriginalFirstThunk)
      continue;
    auto *names =
        reinterpret_cast<IMAGE_THUNK_DATA *>(base + desc->OriginalFirstThunk);
    auto *slots = reinterpret_cast<IMAGE_THUNK_DATA *>(base + desc->FirstThunk);
    for (; names->u1.AddressOfData; ++names, ++slots) {
      if (IMAGE_SNAP_BY_ORDINAL(names->u1.Ordinal))
        continue;
      auto *name = reinterpret_cast<IMAGE_IMPORT_BY_NAME *>(
          base + names->u1.AddressOfData);
      if (std::strcmp(reinterpret_cast<char *>(name->Name), "SetCursorPos") ==
          0) {
        cursor_original = reinterpret_cast<Cursor>(slots->u1.Function);
        patch(reinterpret_cast<void **>(&slots->u1.Function),
              reinterpret_cast<void *>(cursor));
      }
      if (std::strcmp(reinterpret_cast<char *>(name->Name), "SwapBuffers") ==
          0) {
        swap_original = reinterpret_cast<Swap>(slots->u1.Function);
        patch(reinterpret_cast<void **>(&slots->u1.Function),
              reinterpret_cast<void *>(swap));
      }
    }
  }
}
void overlay_shutdown() {
  opened = false;
  if (window && reinterpret_cast<WNDPROC>(
                    GetWindowLongPtr(window, GWLP_WNDPROC)) == wndproc)
    SetWindowLongPtr(window, GWLP_WNDPROC,
                     reinterpret_cast<LONG_PTR>(previous));
  for (auto &p : patches)
    if (*p.slot == p.ours) {
      DWORD old;
      if (VirtualProtect(p.slot, sizeof(void *), PAGE_READWRITE, &old)) {
        *p.slot = p.old;
        DWORD ignored;
        VirtualProtect(p.slot, sizeof(void *), old, &ignored);
      }
    }
  patches.clear();
  for (auto *d : probes)
    d->Release();
  probes.clear();
  if (directinput)
    directinput->Release();
  directinput = nullptr;
}
} // namespace kp::devtools
#else
namespace kp::devtools {
void overlay_tick() {}
void overlay_shutdown() {}
bool overlay_open() { return false; }
unsigned long overlay_input_calls() { return 0; }
} // namespace kp::devtools
#endif
