#include "api/projectiles_entry.hpp"
#if defined(__i386__)
#ifdef _WIN32
#define KP_DISPATCH "_kp_projectile_dispatch"
#else
#define KP_DISPATCH "kp_projectile_dispatch"
#endif
// Keep this exact entry shared with the executable i386 ABI regression test.
// Caller arguments remain at their original addresses. C++ gets an explicit
// original-SP capture and never derives caller context from its own frame.
extern "C" __attribute__((naked)) void kp_projectile_entry() {
  __asm__ volatile("pushfl\n\tpushal\n\t"
                   "movl %esp,%eax\n\tleal 36(%esp),%edx\n\t"
                   "pushl %edx\n\tpushl %eax\n\tcall " KP_DISPATCH "\n\t"
                   "addl $8,%esp\n\tmovl %eax,28(%esp)\n\t"
                   "popal\n\tpopfl\n\tret $12\n\t");
}
#endif
