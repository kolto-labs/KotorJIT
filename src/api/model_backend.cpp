#include "api/model.hpp"
#include <limits>
namespace kp::api::model {
#if (defined(_WIN32) && defined(__i386__)) || (defined(__APPLE__) && (defined(__i386__) || defined(__x86_64__)))
namespace {
#if defined(_WIN32)
#define KP_MODEL_CALL __attribute__((thiscall))
constexpr Abi host_abi=Abi::Win32;
#elif defined(__i386__)
// Darwin i386 passes this on the stack, not in ECX. The ordinary cdecl
// function pointer also preserves the x87 float return convention if needed.
#define KP_MODEL_CALL __attribute__((cdecl))
constexpr Abi host_abi=Abi::Darwin32;
#else
// Darwin x86-64 uses SysV: RDI=this, ESI=id/bool, XMM0=float.
#define KP_MODEL_CALL
constexpr Abi host_abi=Abi::Darwin64;
#endif
class Native final:public Backend {
public:
    Reader reader=nullptr;Logger logger=nullptr;void* context=nullptr;
    Abi abi()const override{return host_abi;}
    unsigned width()const override{return sizeof(void*);}
    bool read(Address address,void* out,std::size_t size)const override {
        if(!reader || address>std::numeric_limits<std::uintptr_t>::max() || size>std::numeric_limits<std::uintptr_t>::max()-address)return false;
        return reader(address,out,size,context);
    }
    std::uint32_t convert(Address f,Address client,std::uint32_t id)override {
        using Call=std::uint32_t(KP_MODEL_CALL *)(void*,std::uint32_t);
        return reinterpret_cast<Call>(static_cast<std::uintptr_t>(f))(ptr(client),id);
    }
    Address creature(Address f,Address client,std::uint32_t id)override {
        using Call=void*(KP_MODEL_CALL *)(void*,std::uint32_t);
        return value(reinterpret_cast<Call>(static_cast<std::uintptr_t>(f))(ptr(client),id));
    }
    Address server_object(Address f,Address server,std::uint32_t id)override {
        return creature(f,server,id); // Same pointer-returning (this,uint32) ABI.
    }
    Address model(Address f,Address creature)override {
        using Call=void*(KP_MODEL_CALL *)(void*,unsigned char,int);
        return value(reinterpret_cast<Call>(static_cast<std::uintptr_t>(f))(ptr(creature),0xff,0));
    }
    bool set_scale(Address f,Address model,float scale)override {
        using Call=bool(KP_MODEL_CALL *)(void*,float,bool);
        return reinterpret_cast<Call>(static_cast<std::uintptr_t>(f))(ptr(model),scale,true);
    }
    void log(const std::string& text)override{if(logger)logger(text,context);}
private:
    static void* ptr(Address value){return reinterpret_cast<void*>(static_cast<std::uintptr_t>(value));}
    static Address value(void* ptr){return reinterpret_cast<std::uintptr_t>(ptr);}
};
}
#endif
Backend* native_backend(Reader read,Logger log,void* context) {
#if (defined(_WIN32) && defined(__i386__)) || (defined(__APPLE__) && (defined(__i386__) || defined(__x86_64__)))
    static Native native;native.reader=read;native.logger=log;native.context=context;return &native;
#else
    (void)read;(void)log;(void)context;return nullptr;
#endif
}
bool bind_native(const std::string& sha,Address base,Reader read,Logger log,void* context,
                 const std::array<Address, 5>* generated_sites,std::string& error) {
    operations().unbind();
    if(!read || !log){error="model binding requires fallible reader and mutation logger";return false;}
    Backend* native=native_backend(read,log,context);
    if(!native){error="unsupported: no native model adapter for host OS/architecture";return false;}
    return operations().bind(sha,base,native,generated_sites,error);
}
}
