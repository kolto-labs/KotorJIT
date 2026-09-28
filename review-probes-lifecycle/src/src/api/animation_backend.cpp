#include "api/animation.hpp"
#include <limits>
namespace kp::api::animation {
#if (defined(_WIN32)&&defined(__i386__))||(defined(__APPLE__)&&(defined(__i386__)||defined(__x86_64__)))
namespace {
#if defined(_WIN32)
#define KP_ANIM_CALL __attribute__((thiscall))
constexpr model::Abi host_abi=model::Abi::Win32;
#elif defined(__i386__)
#define KP_ANIM_CALL __attribute__((cdecl))
constexpr model::Abi host_abi=model::Abi::Darwin32;
#else
#define KP_ANIM_CALL
constexpr model::Abi host_abi=model::Abi::Darwin64;
#endif
class Native final:public Backend {
public:
 model::Reader reader=nullptr;model::Logger logger=nullptr;void* context=nullptr;
 model::Abi abi()const override{return host_abi;}unsigned width()const override{return sizeof(void*);}
 bool read(Address a,void* out,std::size_t size)const override{
  return reader&&a<=UINTPTR_MAX&&size<=UINTPTR_MAX-a&&reader(a,out,size,context);
 }
 bool query(Address function,Address model,const char* name,float& time,float& duration)override{
  using Call=void*(KP_ANIM_CALL *)(void*,const char*,float*,float*);
  time=-1;duration=-1;
  // The returned run pointer is consumed as a Boolean and never retained.
  return reinterpret_cast<Call>(static_cast<std::uintptr_t>(function))(
   reinterpret_cast<void*>(static_cast<std::uintptr_t>(model)),name,&time,&duration)!=nullptr;
 }
 bool play(Address function,Address model,const char* name,float rate,int flags,float start)override{
  using Call=int(KP_ANIM_CALL *)(void*,const char*,float,int,float);
  return reinterpret_cast<Call>(static_cast<std::uintptr_t>(function))(
   reinterpret_cast<void*>(static_cast<std::uintptr_t>(model)),name,rate,flags,start)!=0;
 }
 void log(const std::string& text)override{if(logger)logger(text,context);}
};
}
#endif
bool bind_native(const std::string& sha,Address base,model::Reader read,model::Logger log,void* context,std::string& error){
 operations().unbind();
 if(!read||!log){error="animation binding requires fallible reader and logger";return false;}
#if (defined(_WIN32)&&defined(__i386__))||(defined(__APPLE__)&&(defined(__i386__)||defined(__x86_64__)))
 static Native native;native.reader=read;native.logger=log;native.context=context;
 return operations().bind(sha,base,&model::operations(),&native,error);
#else
 (void)sha;(void)base;(void)context;error="unsupported: no native animation adapter for host OS/architecture";return false;
#endif
}
}
