#pragma once
#include <stdint.h>
#include <mach-o/loader.h>
#ifdef __cplusplus
extern "C" {
#endif
uint32_t _dyld_image_count(void);
const struct mach_header* _dyld_get_image_header(uint32_t image_index);
intptr_t _dyld_get_image_vmaddr_slide(uint32_t image_index);
const char* _dyld_get_image_name(uint32_t image_index);
int _NSGetExecutablePath(char* buf, uint32_t* bufsize);
#ifdef __cplusplus
}
#endif
