#pragma once
#include <objc/runtime.h>
#ifdef __cplusplus
extern "C" {
#endif
void objc_msgSend(void);     /* cast to the exact prototype at each call site */
#ifdef __cplusplus
}
#endif
