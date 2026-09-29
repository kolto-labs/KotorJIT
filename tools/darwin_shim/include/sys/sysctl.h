#pragma once
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
int sysctlbyname(const char* name, void* oldp, size_t* oldlenp, void* newp, size_t newlen);
#ifdef __cplusplus
}
#endif
