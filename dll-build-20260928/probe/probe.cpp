#include <windows.h>
#include <string>
#include <thread>
extern "C" __declspec(dllexport) int probe_fn(int x){ std::string s="hi"; return x + (int)s.size(); }
BOOL WINAPI DllMain(HINSTANCE,DWORD,LPVOID){ return TRUE; }
