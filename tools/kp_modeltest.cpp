#include "api/model.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <vector>
#include <sys/mman.h>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
using namespace kp::api::model;
#define CHECK(x) do{if(!(x))throw std::runtime_error(std::string("line ")+std::to_string(__LINE__)+": "+#x);}while(0)
#include "tests/model_backend_fixture.hpp"
// Operations::bind requires the caller (normally a hookpack-admitted generated
// operation) to hand back which VA it resolved for each of the profile's five
// sites. These controlled-backend tests have no hookpack: they exercise the
// Profile's own compile-time sites as if they were the admitted roles.
std::array<Address, 5> generated_from(const Profile& p) {
 std::array<Address, 5> gen{};
 for (unsigned i = 0; i < gen.size(); ++i) gen[i] = p.sites[i].va;
 return gen;
}
void core_tests(const Profile& p) {
 Fake f(p);Operations op;std::string e;Capture original,after;auto gen=generated_from(p);
 CHECK(!op.bind("wrong",f.base,&f,&gen,e));CHECK(f.setters==0);
 f.host_width=p.width==4?8:4;CHECK(!op.bind(p.sha256,f.base,&f,&gen,e));f.host_width=p.width;
 f.host_abi=p.abi==Abi::Win32?Abi::Darwin32:Abi::Win32;CHECK(!op.bind(p.sha256,f.base,&f,&gen,e));f.host_abi=p.abi;
 CHECK(!op.bind(p.sha256,0,&f,&gen,e));
 auto saved=f.bytes[f.site(0)];f.bytes[f.site(0)]^=1;CHECK(!op.bind(p.sha256,f.base,&f,&gen,e));f.bytes[f.site(0)]=saved;
 CHECK(op.bind(p.sha256,f.base,&f,&gen,e));CHECK(op.snapshot(42,original,e));CHECK(original.client_id==73);
 for(float n:{0.f,-1.f,4.1f,std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN()})CHECK(!op.resize(original,n,after,e));
 CHECK(f.setters==0);CHECK(!op.snapshot(0x7f000000,after,e));
 CHECK(op.resize(original,2,after,e));CHECK(after.base==2&&after.effective==3&&f.setters==1);
 CHECK(op.restore(original,after,e));CHECK(after.base==1&&after.effective==1.5&&f.setters==2);
 CHECK(f.logs.size()==2&&f.logs.back().find("verified=1")!=std::string::npos);
 f.mutate=false;CHECK(!op.resize(original,2,after,e));CHECK(e.find("mismatch")!=std::string::npos);f.mutate=true;
 f.accept=false;CHECK(!op.resize(original,2,after,e));f.accept=true;CHECK(op.restore(original,after,e));
 auto count=f.setters;f.gob+=0x1000;f.setup_model(f.gob,1,1.5);CHECK(!op.resize(original,2,after,e));CHECK(f.setters==count);f.gob-=0x1000;
 f.put<std::uint8_t>(f.actor+p.type_offset,2);CHECK(!op.snapshot(42,after,e));f.put<std::uint8_t>(f.actor+p.type_offset,5);
 f.ptr(f.gob+p.guard_offset,0);CHECK(!op.resize(original,2,after,e));f.ptr(f.gob+p.guard_offset,0x1234);
 f.ptr(f.vt+p.scale_slot,f.site(3)+1);CHECK(!op.snapshot(42,after,e));f.ptr(f.vt+p.scale_slot,f.site(3));
 f.ptr(f.actor+(p.width==8?0x80:0x68),0);CHECK(!op.snapshot(42,after,e));f.ptr(f.actor+(p.width==8?0x80:0x68),f.anim);
 f.bytes.erase(f.gob+p.effective_offset);CHECK(!op.snapshot(42,after,e));f.put(f.gob+p.effective_offset,1.5f);
 f.put(f.gob+p.base_offset,std::numeric_limits<float>::quiet_NaN());CHECK(!op.resize(original,2,after,e));f.put(f.gob+p.base_offset,1.f);
 f.ptr(f.internal+p.internal_array,0);CHECK(!op.snapshot(42,after,e));f.ptr(f.internal+p.internal_array,f.array);
 auto old_actor=f.actor;f.actor=0;CHECK(!op.snapshot(42,after,e));f.actor=old_actor;
 auto old_model=f.gob;f.gob=0;CHECK(!op.snapshot(42,after,e));f.gob=old_model;
 op.unbind();CHECK(!op.resize(original,2,after,e));CHECK(op.bind(p.sha256,f.base,&f,&gen,e));CHECK(!op.restore(original,after,e));
 CHECK(f.setters==count);
 CHECK(op.snapshot(42,original,e));f.replace_after=true;CHECK(!op.resize(original,2,after,e));
 CHECK(e.find("mismatch")!=std::string::npos);
}

void ownership_tests(const Profile& p) {
 Fake f(p);Operations op;std::string error;Identity owner;Capture capture,after;auto gen=generated_from(p);
 CHECK(op.bind(p.sha256,f.base,&f,&gen,error));
 if(p.sites[4].va) {
  auto byte=f.bytes[f.site(4)];f.bytes[f.site(4)]^=1;CHECK(!op.identify(42,owner,error));f.bytes[f.site(4)]=byte;
  f.put(f.server_actor+p.width,99u);CHECK(!op.identify(42,owner,error));f.put(f.server_actor+p.width,42u);
  f.put<std::uint8_t>(f.server_actor+p.type_offset,10);CHECK(!op.identify(42,owner,error));f.put<std::uint8_t>(f.server_actor+p.type_offset,5);
 }
 f.ptr(f.actor+(p.width==8?0x80:0x68),0); // Model not ready, actor identity still exists.
 CHECK(op.identify(42,owner,error));CHECK(op.matches(owner,error));
 CHECK(!op.snapshot(42,capture,error,&owner));
 f.ptr(f.actor+(p.width==8?0x80:0x68),f.anim);
 CHECK(op.snapshot(42,capture,error,&owner));CHECK(op.resize(capture,2,after,error));
 const auto writes=f.setters;
 if(p.sites[4].va) {
  f.server_actor+=0x1000;f.put(f.server_actor+p.width,f.server_id);f.put<std::uint8_t>(f.server_actor+p.type_offset,5);
 } else {
  f.actor+=0x1000;f.put<std::uint8_t>(f.actor+p.type_offset,5);f.ptr(f.actor+(p.width==8?0x80:0x68),f.anim);
 }
 CHECK(!op.matches(owner,error));CHECK(!op.snapshot(42,after,error,&owner));
 CHECK(!op.resize(capture,2,after,error));CHECK(!op.restore(capture,after,error));CHECK(f.setters==writes);
}
void original_conversion_test() {
 // Original Win K1 GOG SHA9c10e045..., VA0x5f2ac0..0x5f2ada.
 // This complete leaf function has no external reads/calls: one uint32 stack
 // input, OBJECT_INVALID comparison, high-bit OR, EAX result and ret4.
 static const unsigned char code[]={0x8b,0x44,0x24,0x04,0x3d,0x00,0x00,0x00,0x7f,
   0x74,0x08,0x0d,0x00,0x00,0x00,0x80,0xc2,0x04,0x00,0xb8,0x00,0x00,0x00,0x7f,0xc2,0x04,0x00};
 void* memory=mmap(nullptr,4096,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
 CHECK(memory!=MAP_FAILED);std::memcpy(memory,code,sizeof(code));CHECK(mprotect(memory,4096,PROT_READ|PROT_EXEC)==0);
 const auto convert=reinterpret_cast<OriginalConvert>(memory);
 CHECK(convert(0x7f000000)==0x7f000000);CHECK(convert(42)==0x8000002a);
 CHECK(convert(0x7fffffff)==0xffffffff);CHECK(convert(0xffffffff)==0xffffffff);
 Fake f(profiles().back());f.original_convert=convert;Operations op;std::string error;Capture capture,after;
 auto gen=generated_from(f.p);
 CHECK(op.bind(f.p.sha256,f.base,&f,&gen,error));
 for(const auto id:{42u,0x7fffffffu,0xffffffffu}) {
  f.server_id=id;f.client_id=convert(id);
  CHECK(op.snapshot(id,capture,error));CHECK(capture.client_id==f.client_id);
  CHECK(op.resize(capture,2,after,error));CHECK(op.restore(capture,after,error));
 }
 CHECK(munmap(memory,4096)==0);
}

int forged(lua_State* L) {
 auto size=lua_objlen(L,1);void* memory=lua_newuserdata(L,size);std::memset(memory,0,size);
 lua_getmetatable(L,1);lua_setmetatable(L,-2);return 1;
}
void lua_tests() {
 Fake f(profiles().back());std::string error;auto gen=generated_from(f.p);CHECK(operations().bind(f.p.sha256,f.base,&f,&gen,error));
 lua_State* L=luaL_newstate();luaL_openlibs(L);register_all(L);lua_pushcfunction(L,forged);lua_setglobal(L,"fake_capture");
 const char* program=R"(
 assert(kp.model.capabilities().available)
 assert(kp.GetFirstPC==nil and nwscript==nil)
 assert(kp.model.snapshot(1.5)==nil)
 assert(kp.model.snapshot('42')==nil)
 local ownership=assert(kp.model.identify(42));assert(kp.model.matches(ownership))
 assert(not pcall(kp.model.matches,newproxy(true)))
 assert(not pcall(kp.model.matches,fake_capture(ownership)))
 local c=assert(kp.model.snapshot(42,ownership));assert(c.base==1 and c.effective==1.5)
 assert(not pcall(function()c.base=7 end))
 assert(not pcall(kp.model.resize,{},2))
 local forged=newproxy(true);debug.setmetatable(forged,debug.getmetatable(c))
 assert(not pcall(kp.model.resize,forged,2))
 assert(not pcall(function()return forged.base end))
 assert(not pcall(kp.model.restore,forged))
 assert(not pcall(kp.model.restore,fake_capture(c)))
 assert(kp.model.resize(c,0/0)==nil)
 local a=assert(kp.model.resize(c,2));assert(a.base==2 and a.effective==3)
 local r=assert(kp.model.restore(c));assert(r.base==1 and r.effective==1.5)
 )";
 if(luaL_dostring(L,program)!=0)throw std::runtime_error(lua_tostring(L,-1));
 lua_close(L);operations().unbind();
}
int main(){try{for(const auto& p:profiles()){core_tests(p);ownership_tests(p);}original_conversion_test();lua_tests();std::cout<<"model profiles/core/Lua checks passed (4 layouts, controlled backend; no live ABI proof)\n";return 0;}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
