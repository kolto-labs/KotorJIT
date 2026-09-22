#include "api/model.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
#include <vector>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
using namespace kp::api::model;
#define CHECK(x) do{if(!(x))throw std::runtime_error(std::string("line ")+std::to_string(__LINE__)+": "+#x);}while(0)
struct Fake:Backend {
 const Profile& p;std::map<Address,unsigned char> bytes;
 Address base,manager=0x1000000,client=0x1001000,internal=0x1002000,array=0x1003000,actor=0x1004000,anim=0x1005000,gob=0x1006000,vt=0x1007000;
 unsigned setters=0,conversions=0,lookups=0;std::vector<std::string> logs;
 bool mutate=true,accept=true,replace_after=false;unsigned host_width;Abi host_abi;
 explicit Fake(const Profile& profile):p(profile),base(p.preferred_base+0x10000),host_width(p.width),host_abi(p.abi){
  for(unsigned i=0;i<4;++i)for(unsigned j=0;j<16;++j) {
   auto digit=[](char c){return c<='9'?c-'0':c-'a'+10;};
   bytes[site(i)+j]=(digit(p.sites[i].bytes[j*2])<<4)|digit(p.sites[i].bytes[j*2+1]);
  }
  ptr(base+p.manager_slot-p.preferred_base,manager);ptr(manager+p.manager_client,client);
  ptr(client+p.client_internal,internal);ptr(internal+p.internal_array,array);put<std::uint8_t>(array,1);
  put<std::uint8_t>(actor+p.type_offset,5);ptr(actor+(p.width==8?0x80:0x68),anim);put<std::uint8_t>(anim,1);
  setup_model(gob,1,1.5f);
 }
 void setup_model(Address address,float base_scale,float effective){
  ptr(address+p.guard_offset,0x1234);ptr(address,vt);ptr(vt+p.scale_slot,site(3));
  put(address+p.base_offset,base_scale);put(address+p.effective_offset,effective);
 }
 Address site(unsigned i)const{return base+p.sites[i].va-p.preferred_base;}
 template<class T>void put(Address address,T value){const auto* b=reinterpret_cast<const unsigned char*>(&value);for(unsigned i=0;i<sizeof(value);++i)bytes[address+i]=b[i];}
 void ptr(Address a,Address value){if(p.width==4)put(a,static_cast<std::uint32_t>(value));else put(a,value);}
 template<class T>T get(Address address){T value{};CHECK(read(address,&value,sizeof(value)));return value;}
 Abi abi()const override{return host_abi;}unsigned width()const override{return host_width;}
 bool read(Address a,void* out,std::size_t n)const override{auto* b=static_cast<unsigned char*>(out);for(std::size_t i=0;i<n;++i){auto it=bytes.find(a+i);if(it==bytes.end())return false;b[i]=it->second;}return true;}
 std::uint32_t convert(Address f,Address c,std::uint32_t id)override{CHECK(f==site(0)&&c==client&&id==42);++conversions;return 73;}
 Address creature(Address f,Address c,std::uint32_t id)override{CHECK(f==site(1)&&c==client&&id==73);CHECK(conversions>lookups);++lookups;return actor;}
 Address model(Address f,Address c)override{CHECK(f==site(2)&&c==actor);return gob;}
 bool set_scale(Address f,Address m,float scale)override{
  CHECK(f==site(3)&&m==gob);++setters;
  if(mutate){float ratio=get<float>(gob+p.effective_offset)/get<float>(gob+p.base_offset);put(gob+p.effective_offset,ratio*scale);put(gob+p.base_offset,scale);}
  if(replace_after){gob+=0x2000;setup_model(gob,1,1.5);}
  return accept;
 }
 void log(const std::string& message)override{logs.push_back(message);}
};
void core_tests(const Profile& p) {
 Fake f(p);Operations op;std::string e;Capture original,after;
 CHECK(!op.bind("wrong",f.base,&f,e));CHECK(f.setters==0);
 f.host_width=p.width==4?8:4;CHECK(!op.bind(p.sha256,f.base,&f,e));f.host_width=p.width;
 f.host_abi=p.abi==Abi::Win32?Abi::Darwin32:Abi::Win32;CHECK(!op.bind(p.sha256,f.base,&f,e));f.host_abi=p.abi;
 CHECK(!op.bind(p.sha256,0,&f,e));
 auto saved=f.bytes[f.site(0)];f.bytes[f.site(0)]^=1;CHECK(!op.bind(p.sha256,f.base,&f,e));f.bytes[f.site(0)]=saved;
 CHECK(op.bind(p.sha256,f.base,&f,e));CHECK(op.snapshot(42,original,e));CHECK(original.client_id==73);
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
 op.unbind();CHECK(!op.resize(original,2,after,e));CHECK(op.bind(p.sha256,f.base,&f,e));CHECK(!op.restore(original,after,e));
 CHECK(f.setters==count);
 CHECK(op.snapshot(42,original,e));f.replace_after=true;CHECK(!op.resize(original,2,after,e));
 CHECK(e.find("mismatch")!=std::string::npos);
}

int forged(lua_State* L) {
 auto size=lua_objlen(L,1);void* memory=lua_newuserdata(L,size);std::memset(memory,0,size);
 lua_getmetatable(L,1);lua_setmetatable(L,-2);return 1;
}
void lua_tests() {
 Fake f(profiles().back());std::string error;CHECK(operations().bind(f.p.sha256,f.base,&f,error));
 lua_State* L=luaL_newstate();luaL_openlibs(L);register_all(L);lua_pushcfunction(L,forged);lua_setglobal(L,"fake_capture");
 const char* program=R"(
 assert(kp.model.capabilities().available)
 assert(kp.GetFirstPC==nil and nwscript==nil)
 assert(kp.model.snapshot(1.5)==nil)
 assert(kp.model.snapshot('42')==nil)
 local c=assert(kp.model.snapshot(42));assert(c.base==1 and c.effective==1.5)
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
int main(){try{for(const auto& p:profiles())core_tests(p);lua_tests();std::cout<<"model profiles/core/Lua checks passed (4 layouts, controlled backend; no live ABI proof)\n";return 0;}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
