#pragma once
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef int kern_return_t;
typedef unsigned int mach_port_t;
typedef mach_port_t vm_map_t;
typedef mach_port_t vm_map_read_t;
typedef int vm_prot_t;
typedef unsigned int vm_inherit_t;
typedef int vm_behavior_t;
typedef unsigned int mach_msg_type_number_t;
typedef int boolean_t;
typedef int vm_region_flavor_t;
typedef int* vm_region_info_t;
typedef unsigned long long memory_object_offset_t;
typedef uint64_t mach_vm_address_t;
typedef uint64_t mach_vm_size_t;
typedef int thread_act_t;
#define KERN_SUCCESS 0
#define KERN_NO_SPACE 3
#define MACH_PORT_NULL 0
#ifndef FALSE
#define FALSE 0
#endif
#ifndef TRUE
#define TRUE 1
#endif
#define VM_PROT_NONE ((vm_prot_t)0x00)
#define VM_PROT_READ ((vm_prot_t)0x01)
#define VM_PROT_WRITE ((vm_prot_t)0x02)
#define VM_PROT_EXECUTE ((vm_prot_t)0x04)
#define VM_PROT_COPY ((vm_prot_t)0x10)
#define VM_FLAGS_FIXED 0x0000
#define VM_FLAGS_ANYWHERE 0x0001
#define VM_REGION_BASIC_INFO_64 9
#pragma pack(push, 4)
struct vm_region_basic_info_64 {
    vm_prot_t protection;
    vm_prot_t max_protection;
    vm_inherit_t inheritance;
    boolean_t shared;
    boolean_t reserved;
    memory_object_offset_t offset;
    vm_behavior_t behavior;
    unsigned short user_wired_count;
};
#pragma pack(pop)
typedef struct vm_region_basic_info_64 vm_region_basic_info_data_64_t;
#define VM_REGION_BASIC_INFO_COUNT_64 \
    ((mach_msg_type_number_t)(sizeof(vm_region_basic_info_data_64_t) / sizeof(int)))
extern mach_port_t mach_task_self_;
#define mach_task_self() mach_task_self_
kern_return_t mach_port_deallocate(mach_port_t task, mach_port_t name);
const char* mach_error_string(kern_return_t error_value);
/* <sys/errno.h> on Darwin; declared here so the shim needs no errno.h of its own. */
int* __error(void);
#ifdef __cplusplus
}
#endif
