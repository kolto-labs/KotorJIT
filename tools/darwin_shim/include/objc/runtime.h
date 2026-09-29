#pragma once
#include <stdint.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct objc_class* Class;
typedef struct objc_object* id;
typedef struct objc_selector* SEL;
typedef struct objc_method* Method;
typedef void (*IMP)(void);   /* OBJC_OLD_DISPATCH_PROTOTYPES=0, the SDK default */
typedef signed char BOOL;    /* x86_64 */
#define YES ((BOOL)1)
#define NO ((BOOL)0)
Class objc_getClass(const char* name);
Class object_getClass(id obj);
SEL sel_registerName(const char* str);
Method class_getInstanceMethod(Class cls, SEL name);
IMP method_getImplementation(Method m);
IMP method_setImplementation(Method m, IMP imp);
const char* method_getTypeEncoding(Method m);
BOOL class_addMethod(Class cls, SEL name, IMP imp, const char* types);
IMP class_replaceMethod(Class cls, SEL name, IMP imp, const char* types);
Class class_getSuperclass(Class cls);
const char* class_getName(Class cls);
#ifdef __cplusplus
}
#endif
