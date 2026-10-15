// Offline x86 ABI/dispatch checks. Never loads or launches the game.
#include "hooks/lua_bridge.hpp"
#include "api/memory.hpp"
#include <cstdio>
#include <cstring>
#include <csignal>
#include <csetjmp>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
using namespace kp::hooks;
namespace bridge=kp::hooks::lua_bridge;
namespace {
int failures=0, pre_calls=0, post_calls=0, mode=0;
bool enabled=true;
void check(bool ok,const char* text) {std::printf("%s %s\n",ok?"PASS":"FAIL",text);failures+=!ok;}
bool gate(){return enabled;}
bool reviewed(const Site&){return true;}
bool plain_guard(bridge::Entry&,void(*fn)(void*),void* p){fn(p);return true;}
#define TARGET __attribute__((noinline,noclone,aligned(4096)))
int TARGET ctarget(int a,int b) {asm volatile("nop; nop; nop; nop; nop");return a+b;}
int TARGET __attribute__((stdcall)) starget(int a,int b) {asm volatile("nop; nop; nop; nop; nop");return a+b;}
struct Object {int n;}; Object object{7},other{20};
int TARGET __attribute__((thiscall)) ttarget(Object* o,int a,int b) {asm volatile("nop; nop; nop; nop; nop");return o->n+a+b;}
int TARGET __attribute__((fastcall)) ftarget(int a,int b,int c) {asm volatile("nop; nop; nop; nop; nop");return a+b+c;}
long double TARGET dtarget(int a) {asm volatile("nop; nop; nop; nop; nop");return 1.25L+a;}
long long TARGET qtarget(int a) {asm volatile("nop; nop; nop; nop; nop");return 0x123400000000LL+a;}
void TARGET __attribute__((used)) end_target_pages() {asm volatile("nop");}
using C=int(*)(int,int); C volatile call_c=ctarget;
using S=int(__attribute__((stdcall)) *)(int,int); S volatile call_s=starget;
using T=int(__attribute__((thiscall)) *)(Object*,int,int); T volatile call_t=ttarget;
using F=int(__attribute__((fastcall)) *)(int,int,int); F volatile call_f=ftarget;
using D=long double(*)(int); D volatile call_d=dtarget;
using Q=long long(*)(int); Q volatile call_q=qtarget;

AbiParam arg(int i,int stack,const char* reg="") {return {i,4,stack,"int","integer",reg};}
Site site(const char* name,const char* conv,int stack,void* target) {
    Site s;s.name=name;s.resolved=true;s.addr=reinterpret_cast<std::uintptr_t>(target);
    auto& a=s.abi;a.convention=conv;a.stack_bytes=stack;a.ret_pop=std::strcmp(conv,"cdecl")?stack:0;
    a.cleanup_by=a.ret_pop || std::strcmp(conv,"cdecl")?"callee":"caller";
    a.confidence="proven";a.hook_safe="static_ok";a.engine_accept=true;
    a.variadic=a.struct_return=false;a.ret_storage="EAX";a.ret_type="int";a.ret_lua="integer";
    a.pre=a.post=a.rewrite=a.override_return=a.skip=true;a.observed_ret={a.ret_pop};
    if(!std::strcmp(conv,"thiscall"))a.this_reg="ECX";
    for(int i=0;i<stack/4;++i)a.params.push_back(arg(i,4+i*4));
    s.expected.assign(static_cast<unsigned char*>(target),static_cast<unsigned char*>(target)+5);
    return s;
}
bool dispatch(void*,bridge::Entry& e,bridge::HookCtx& c,bool post) {
    if(post) {
        ++post_calls;
        if(mode==4){c.eax=999;return false;}
        if(e.site.abi.ret_storage=="EAX")c.eax+=100;
        return true;
    }
    ++pre_calls;
    if(mode==1){c.eax=77;c.skip=true;return true;}
    if(mode==2){c.args[0]=999;c.ecx=0;return false;}
    if(mode==3){check(call_c(4,5)==9,"recursive entry bypasses handlers");return true;}
    if(mode==4)return true;
    if(mode==5){e.poisoned.store(true);return false;}
    if(e.site.abi.ret_storage!="EAX")return true;
    c.args[0]=10;
    if(e.site.abi.convention=="thiscall")c.ecx=reinterpret_cast<std::uintptr_t>(&other);
    if(e.site.abi.convention=="fastcall"){c.ecx=10;c.edx=20;c.args[0]=30;}
    return true;
}
template<class Fn> void exercise(Site s,Fn call,int baseline,int changed) {
    bridge::Entry e;std::string error;
    bool ok=e.install(s,s.addr,dispatch,nullptr,gate,error);
    check(ok,(s.name+" install: "+error).c_str());if(!ok)return;
    mode=0;pre_calls=post_calls=0;check(call()==changed,"pre/argument rewrite/post return");
    check(pre_calls==1 && post_calls==1,"one pre and one post");
    mode=1;check(call()==177,"skip with return override and post");
    mode=2;check(call()==baseline,"pre error restores original arguments and this");
    mode=4;check(call()==baseline,"post error preserves original return without replay");
    mode=0;std::uintptr_t before,after;
    asm volatile("mov %%esp,%0":"=m"(before));
    for(int i=0;i<1000;++i)call();
    asm volatile("mov %%esp,%0":"=m"(after));check(before==after,"ESP balance over 1000 calls");
    enabled=false;check(call()==baseline,"disabled runtime forwards unchanged");enabled=true;
    mode=5;check(call()==baseline,"poison forwards original");
    int saved=pre_calls;check(call()==baseline && pre_calls==saved,"poison is permanent per entry");
    check(e.uninstall(),"uninstall");check(call()==baseline,"original restored");
}
void native_checks() {
    exercise(site("cdecl","cdecl",8,reinterpret_cast<void*>(ctarget)),[]{return call_c(2,3);},5,113);
    exercise(site("stdcall","stdcall",8,reinterpret_cast<void*>(starget)),[]{return call_s(2,3);},5,113);
    exercise(site("thiscall","thiscall",8,reinterpret_cast<void*>(ttarget)),[]{return call_t(&object,2,3);},12,133);
    auto f=site("fastcall","fastcall",4,reinterpret_cast<void*>(ftarget));
    f.abi.params={arg(0,-1,"ECX"),arg(1,-1,"EDX"),arg(2,4)};
    exercise(f,[]{return call_f(2,3,4);},9,160);
    auto c=site("recursive","cdecl",8,reinterpret_cast<void*>(ctarget));
    {bridge::Entry e;std::string error;check(e.install(c,c.addr,dispatch,nullptr,gate,error),"recursion install");
        mode=3;pre_calls=0;check(call_c(2,3)==105 && pre_calls==1,"per-site recursion guard");}
    auto d=site("float","cdecl",4,reinterpret_cast<void*>(dtarget));d.abi.ret_storage="ST0";d.abi.ret_lua="number";
    {bridge::Entry e;std::string error;check(e.install(d,d.addr,dispatch,nullptr,gate,error),"ST0 install");
        mode=0;check(call_d(3)==4.25L,"x87 extended-precision passthrough");}
    auto q=site("int64","cdecl",4,reinterpret_cast<void*>(qtarget));q.abi.ret_storage="EDX:EAX";q.abi.ret_lua="int64";
    {bridge::Entry e;std::string error;check(e.install(q,q.addr,dispatch,nullptr,gate,error),"EDX:EAX install");
        mode=0;check(call_q(3)==0x123400000003LL,"EDX:EAX passthrough");}
    auto bad=c;bad.abi.confidence="declared_only";check(!bridge::refusal(bad).empty(),"refuse declared ABI");
    bad=c;bad.abi.ret_pop=4;check(!bridge::refusal(bad).empty(),"refuse cdecl cleanup mismatch");
    bad=f;bad.abi.ret_pop=0;check(!bridge::refusal(bad).empty(),"refuse fastcall cleanup mismatch");
    bad=c;bad.abi.params.clear();check(!bridge::refusal(bad).empty(),"refuse incomplete parameter contract");
    bad=c;bad.abi.params[1].stack=4;check(!bridge::refusal(bad).empty(),"refuse overlapping parameters");
    bad=c;bad.abi.variadic=true;check(!bridge::refusal(bad).empty(),"refuse variadic");
    bad=c;bad.abi.struct_return=true;check(!bridge::refusal(bad).empty(),"refuse struct return");
    bad=c;bad.abi.observed_ret={4};check(!bridge::refusal(bad).empty(),"refuse conflicting evidence");
    bad=c;bad.hook_refused=true;check(!bridge::refusal(bad).empty(),"refuse unsafe prologue");
}
int lua_call_target(lua_State* L){lua_pushinteger(L,call_c(luaL_checkinteger(L,1),luaL_checkinteger(L,2)));return 1;}
void script(lua_State* L,const char* text) {
    int st=luaL_dostring(L,text);check(st==0,st?lua_tostring(L,-1):text);if(st)lua_pop(L,1);
}
void lua_checks() {
    std::string expected;const auto* bytes=reinterpret_cast<unsigned char*>(ctarget);
    char hex[3];for(int i=0;i<19;++i){std::snprintf(hex,3,"%02x",bytes[i]);expected+=hex;}
    std::string json=R"({"format":"agentdecompile.hookmanifest/v1","program":{"slug":"synthetic","image_base":0},"functions":[{"id":"sum","abi":{"convention":"cdecl","stack_arg_bytes":8,"cleanup":{"by":"caller","ret_imm16":0},"variadic":false,"struct_return":false,"abi_confidence":"proven","ret":{"storage":"EAX","c_type":"int","lua":"integer"},"params":[{"i":0,"size":4,"storage":{"stack":4},"c_type":"int","lua":"integer"},{"i":1,"size":4,"storage":{"stack":8},"c_type":"int","lua":"integer"}],"evidence":{"ret_imm_observed":[0]}},"hook":{"safe":"static_ok","kp_engine_would_accept":true},"lua":{"pre":true,"post":true,"can_rewrite_args":true,"can_override_return":true,"can_skip_original":true},"locate":{"expected_bytes_unmasked_count":1,"expected_bytes":")"+expected+R"("}}]})";
    AddressTable t;std::string error;check(AddressTable::parse_manifest(json,"synthetic",t,error),"parse ABI manifest");
    kp::api::memory::bind_scan_regions(0,{{reinterpret_cast<std::uintptr_t>(ctarget),64,"synthetic"}});
    t.resolve_from_signatures(0);
    check(t.find("sum") && t.find("sum")->resolved,"resolve synthetic site by bytes");
    lua_State* L=luaL_newstate();luaL_openlibs(L);bridge::register_all(L);
    lua_pushcfunction(L,lua_call_target);lua_setglobal(L,"target");
    bridge::bind(&t,0,gate,gate,plain_guard);
    script(L,"local ok,err=pcall(kp.hook.pre,'sum',function()end);assert(not ok and err:find('reviewed'))");
    bridge::bind(&t,0,gate,gate,plain_guard,reviewed);
    script(L,"pre=kp.hook.pre('sum',function(c) saved=c; oldargs=c.args; c.args[1]=10 end); post=kp.hook.post('sum',function(c) c.ret=c.ret+100 end); assert(target(2,3)==113)");
    script(L,"assert(not pcall(function()return saved.ret end));assert(not pcall(function()return oldargs[1] end))");
    script(L,"pre:remove();post:remove();assert(target(2,3)==5)");
    script(L,"pre=kp.hook.pre('sum',function(c)c.args[1]=99;error('expected error')end);assert(target(2,3)==5);pre:remove()");
    script(L,"pre=kp.hook.pre('sum',function(c)c.args[1]=4294967296 end);assert(target(2,3)==5);pre:remove()");
    script(L,"pre=kp.hook.pre('sum',function(c)c:skip(55)end);post=kp.hook.post('sum',function(c)c.ret=c.ret+1 end);assert(target(2,3)==56);pre:remove();post:remove()");
    script(L,"pre=kp.hook.pre('sum',function(c)assert(target(4,5)==9);c.args[2]=7 end);assert(target(2,3)==9);pre:remove()");
    script(L,"post=kp.hook.post('sum',function(c)c.ret=99;error('post failure')end);assert(target(2,3)==5);post:remove()");
    script(L,"pre=kp.hook.pre('sum',function(c)collectgarbage();c.args[1]=20 end);assert(target(2,3)==23)");
    lua_close(L);check(call_c(2,3)==5,"state finalizer removes handlers before closed VM reuse");
    bridge::shutdown();check(call_c(2,3)==5,"bridge shutdown restores original");
}
// Offline equivalent of FaultFrame: injected guard claims one actual signal,
// poisons the site, and disables future VM dispatch. No game handlers touched.
sigjmp_buf recovery;
void fault_handler(int){siglongjmp(recovery,1);}
bool fault_guard(bridge::Entry& e,void(*fn)(void*),void* p) {
    if(sigsetjmp(recovery,1)){e.poisoned.store(true);enabled=false;return false;}
    fn(p);return true;
}
void fault_work(void*){std::raise(SIGSEGV);}
bool fault_dispatch(void*,bridge::Entry& e,bridge::HookCtx& c,bool post) {
    if(post)return true;
    c.args[0]=999;return fault_guard(e,fault_work,nullptr);
}
void fault_check() {
    struct sigaction action{},old{};action.sa_handler=fault_handler;sigemptyset(&action.sa_mask);
    sigaction(SIGSEGV,&action,&old);
    auto s=site("fault","cdecl",8,reinterpret_cast<void*>(ctarget));
    {bridge::Entry e;std::string error;check(e.install(s,s.addr,fault_dispatch,nullptr,gate,error),"fault entry install");
        check(call_c(2,3)==5 && e.poisoned,"fault recovers, rolls back args, poisons site");
        enabled=true;check(call_c(2,3)==5,"poison remains after runtime re-enable");}
    sigaction(SIGSEGV,&old,nullptr);
}
}
int main(){std::setvbuf(stdout,nullptr,_IONBF,0);native_checks();lua_checks();fault_check();std::printf("%d failures\n",failures);return failures?1:0;}
