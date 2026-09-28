// kp.motion Stage M1 offline tests: profile gating, exact guards, the server
// lookup chain, placeable fences, value checks, the protected Lua surface and
// a read-only cross-check against data/addresses/k1_gog_103.json.
// Synthetic memory only; this proves nothing about the live game.
// Usage: kp_motiontest [source-root]
#include "api/motion.hpp"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <functional>
#include <iostream>
#include <limits>
#include <map>
#include <sstream>
#include <stdexcept>
#include <string>
#include <vector>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
using namespace kp::api::motion;
#define CHECK(x) do{if(!(x))throw std::runtime_error(std::string("line ")+std::to_string(__LINE__)+": "+#x);}while(0)

namespace {
unsigned checks=0;
#define COUNT(x) do{CHECK(x);++checks;}while(0)
const Profile& k1(){return profiles().front();}
std::string source_root=".";

// Sparse synthetic memory. Only mapped bytes are readable. The typed getter is
// modelled as a lookup table and counts every call so a test can prove that a
// refusal happened before the engine was reached.
struct MotionFake:Backend {
 const Profile& p;std::map<Address,unsigned char> bytes;
 Address base;
 Address manager=0x1000000,server=0x1001000,internal=0x1002000,array=0x1003000,crate=0x1004000;
 std::map<std::uint32_t,Address> objects;
 unsigned calls=0;std::vector<std::uint32_t> ids;
 unsigned host_width;Abi host_abi;
 explicit MotionFake(const Profile& profile):p(profile),base(p.preferred_base),host_width(p.width),host_abi(p.abi){
  for(const auto& s:p.spans)if(s.va){
   auto digit=[](char c){return c<='9'?c-'0':c-'a'+10;};
   for(std::size_t j=0;j*2<std::strlen(s.hex);++j)bytes[s.va+j]=(digit(s.hex[j*2])<<4)|digit(s.hex[j*2+1]);
  }
  for(const auto& s:p.slots)if(s.va)ptr(s.va,s.target);
  ptr(p.manager_slot,manager);ptr(manager+p.manager_server,server);ptr(server+p.server_internal,internal);
  ptr(internal+p.internal_array,array);put<std::uint8_t>(array,1);
  placeable(crate,42);
 }
 void placeable(Address o,std::uint32_t id){
  ptr(o,p.placeable_vtable);put(o+p.id,id);put<std::uint8_t>(o+p.type,p.placeable_type);
  put<std::uint32_t>(o+p.area_id,0x7f000123);
  put(o+p.position,1.5f);put(o+p.position+4,-2.25f);put(o+p.position+8,0.125f);
  put(o+p.orientation,0.f);put(o+p.orientation+4,1.f);put(o+p.orientation+8,0.f);
  put<std::uint32_t>(o+p.push_gate,1);put<std::uint32_t>(o+p.dirty,0);
  put<std::int32_t>(o+p.aabb_marker,3);
  put(o+p.quaternion,1.f);put(o+p.quaternion+4,0.f);put(o+p.quaternion+8,0.f);put(o+p.quaternion+12,0.f);
  objects[id]=o;
 }
 template<class T>void put(Address a,T value){const auto* b=reinterpret_cast<const unsigned char*>(&value);for(unsigned i=0;i<sizeof(value);++i)bytes[a+i]=b[i];}
 void ptr(Address a,Address value){put(a,static_cast<std::uint32_t>(value));}
 void unmap(Address a,std::size_t n){for(std::size_t i=0;i<n;++i)bytes.erase(a+i);}
 Abi abi()const override{return host_abi;}
 unsigned width()const override{return host_width;}
 bool read(Address a,void* out,std::size_t n)const override{
  auto* b=static_cast<unsigned char*>(out);
  for(std::size_t i=0;i<n;++i){auto it=bytes.find(a+i);if(it==bytes.end())return false;b[i]=it->second;}
  return true;
 }
 Address placeable(Address f,Address s,std::uint32_t id)override{
  CHECK(f==p.get_placeable);CHECK(s==server);++calls;ids.push_back(id);
  auto it=objects.find(id);return it==objects.end()?0:it->second;
 }
};

bool untouched(const Capture& c){
 Capture d;
 return c.epoch==d.epoch && c.id==d.id && c.object==d.object && c.area_id==d.area_id && c.position==d.position &&
        c.orientation==d.orientation && c.facing==d.facing && c.push_gate_raw==d.push_gate_raw &&
        c.dirty_position==d.dirty_position && c.dirty_orientation==d.dirty_orientation &&
        c.collision_registered==d.collision_registered && c.quaternion_raw==d.quaternion_raw;
}
// Every refusal: false, the expected kind, zero-state output, and (if asked)
// no engine call.
void refuses(Operations& op,MotionFake& f,std::uint32_t id,Failure kind,bool before_call){
 Capture c;std::string e;unsigned calls=f.calls;
 COUNT(!op.capture(id,c,e));COUNT(op.last_failure()==kind);COUNT(untouched(c));
 COUNT(e.rfind(failure_name(kind),0)==0);
 if(before_call)COUNT(f.calls==calls);
}

// --- tests (names follow fanout-lua-lifecycle-plan.md Track M, M1) ------------
void unsupported_profile_capabilities_false() {
 COUNT(profiles().size()==1);COUNT(std::string(k1().name)=="windows-k1-gog");
 MotionFake f(k1());Operations op;std::string e;
 for(const char* sha:{"aa6283733d3c738d11d12453f77dfc6b7e87f95326a07ee97daab1a37734b032", // macOS K1
     "f14f285b1b6ed7e4bf000fe19ebcd0d6528d1d3e86d2832be6092761557c130d",                   // macOS K2 i386
     "469067c416f1a3ff391df73c7ace2d44a8d0a246253e8ad5752f6413ea033be4",                   // macOS K2 x86_64
     "34e6d971c034222a417995d8e1e8fdd9f8781795c9c289bd86c499a439f34c88",                   // K1 Steam
     "2719ed2cb678e2c1ff5b2a787f9804d8e5f8dd52a02c2279080f031636e03a05",                   // K1 Steam unpacked
     "777bee235a9e8bdd9863f6741bc3ac54bb6a113b62b1d2e4d12bbe6db963a914",                   // K2 GOG Aspyr
     "6a522e71631dcee93467bd2010f3b23d9145326e1e2e89305f13ab104dbbffef",                   // K2 Steam Aspyr
     "", "wrong"}) {
  COUNT(!op.bind(sha,f.base,&f,e));COUNT(op.last_failure()==Failure::Unsupported);COUNT(!op.available());
  COUNT(e.rfind("unsupported",0)==0);
 }
 COUNT(!op.bind(k1().sha256,f.base,nullptr,e));COUNT(op.last_failure()==Failure::Unsupported);
 f.host_width=8;COUNT(!op.bind(k1().sha256,f.base,&f,e));COUNT(op.last_failure()==Failure::Unsupported);f.host_width=4;
 f.host_abi=Abi::Darwin32;COUNT(!op.bind(k1().sha256,f.base,&f,e));COUNT(op.last_failure()==Failure::Unsupported);f.host_abi=Abi::Win32;
 COUNT(!op.bind(k1().sha256,0,&f,e));COUNT(op.last_failure()==Failure::Unsupported);
 // Absent profile: an unbound capture is a typed unsupported refusal, no call.
 refuses(op,f,42,Failure::Unsupported,true);
 // This Linux test host has no native adapter.
 COUNT(native_backend([](kp::api::model::Address,void*,std::size_t,void*){return false;},nullptr)==nullptr);
 COUNT(!bind_native(k1().sha256,0x400000,[](kp::api::model::Address,void*,std::size_t,void*){return false;},nullptr,e));
 COUNT(!bind_native(k1().sha256,0x400000,nullptr,nullptr,e));
 COUNT(!operations().available());
 COUNT(f.calls==0);
 COUNT(op.bind(k1().sha256,f.base,&f,e));COUNT(op.available());COUNT(op.last_failure()==Failure::None);
}

void relocated_image_refused() {
 // Spans embed absolute immediates (0x7a39fc, 0x746638, 0x7494d0).
 MotionFake f(k1());Operations op;std::string e;
 COUNT(!op.bind(k1().sha256,f.base+0x10000,&f,e));COUNT(op.last_failure()==Failure::Unsupported);
 COUNT(e.find("relocated")!=std::string::npos);COUNT(f.calls==0);
}

void span_table_valid() {
 unsigned n=0;
 for(const auto& s:k1().spans)if(s.va){COUNT(Operations::valid_span(s));++n;}
 COUNT(n==23);
 COUNT(!Operations::valid_span({0x1000,""}));
 COUNT(!Operations::valid_span({0x1000,"8b490"}));
 COUNT(!Operations::valid_span({0x1000,"8B4904"}));
 COUNT(!Operations::valid_span({0x1000,"8g4904"}));
 COUNT(!Operations::valid_span({0x1000,"00112233445566778899aabbccddeeff00"}));
 COUNT(Operations::valid_span({0x1000,"00112233445566778899aabbccddeeff"}));
 COUNT(!Operations::valid_span({0x1000,nullptr}));
}

void guard_flip_refuses_before_call() {
 unsigned bytes=0;
 for(const auto& s:k1().spans) {
  if(!s.va)continue;
  for(std::size_t j=0;j*2<std::strlen(s.hex);++j) {
   ++bytes;
   MotionFake f(k1());Operations op;std::string e;
   f.bytes[s.va+j]^=0x01;
   COUNT(!op.bind(k1().sha256,f.base,&f,e));COUNT(op.last_failure()==Failure::Guard);COUNT(!op.available());
   f.bytes[s.va+j]^=0x01;
   COUNT(op.bind(k1().sha256,f.base,&f,e));
   f.bytes[s.va+j]^=0x80;                       // flipped after bind: every capture re-checks
   refuses(op,f,42,Failure::Guard,true);
   f.bytes[s.va+j]^=0x80;
   f.unmap(s.va+j,1);                           // unreadable guard byte
   refuses(op,f,42,Failure::Guard,true);
   COUNT(f.calls==0);
  }
 }
 COUNT(bytes>100);
 for(const auto& s:k1().slots) {
  MotionFake f(k1());Operations op;std::string e;
  f.ptr(s.va,s.target+1);
  COUNT(!op.bind(k1().sha256,f.base,&f,e));COUNT(op.last_failure()==Failure::Guard);
  f.ptr(s.va,s.target);COUNT(op.bind(k1().sha256,f.base,&f,e));
  f.ptr(s.va,0);refuses(op,f,42,Failure::Guard,true);
 }
}

void chain_failure_refuses_before_call() {
 const Profile& p=k1();
 struct Case{const char* what;std::function<void(MotionFake&)> breakit;};
 std::vector<Case> cases{
  {"manager null",[&](MotionFake& f){f.ptr(p.manager_slot,0);}},
  {"manager unreadable",[&](MotionFake& f){f.unmap(p.manager_slot,4);}},
  {"server null",[&](MotionFake& f){f.ptr(f.manager+p.manager_server,0);}},
  {"internal null",[&](MotionFake& f){f.ptr(f.server+p.server_internal,0);}},
  {"array null",[&](MotionFake& f){f.ptr(f.internal+p.internal_array,0);}},
  {"array unreadable",[&](MotionFake& f){f.unmap(f.array,1);}},
 };
 for(auto& c:cases) {
  MotionFake f(p);Operations op;std::string e;COUNT(op.bind(p.sha256,f.base,&f,e));
  c.breakit(f);refuses(op,f,42,Failure::Chain,true);
 }
}

void invalid_object_id_refused_before_call() {
 MotionFake f(k1());Operations op;std::string e;COUNT(op.bind(k1().sha256,f.base,&f,e));
 refuses(op,f,0x7f000000,Failure::Identity,true);
}

void non_placeable_type_refuses() {
 for(std::uint8_t type:{std::uint8_t(5),std::uint8_t(10),std::uint8_t(6),std::uint8_t(0)}) {
  MotionFake f(k1());Operations op;std::string e;COUNT(op.bind(k1().sha256,f.base,&f,e));
  f.put<std::uint8_t>(f.crate+k1().type,type);
  refuses(op,f,42,Failure::Identity,false);COUNT(f.calls==1);
 }
 // Unknown id: the getter returns null.
 MotionFake f(k1());Operations op;std::string e;COUNT(op.bind(k1().sha256,f.base,&f,e));
 refuses(op,f,77,Failure::Identity,false);COUNT(f.calls==1&&f.ids.back()==77);
}

void wrong_vtable_refuses() {
 for(Address vt:{Address(0x745f18),Address(0x7494d4),Address(0)}) {
  MotionFake f(k1());Operations op;std::string e;COUNT(op.bind(k1().sha256,f.base,&f,e));
  f.ptr(f.crate,vt);refuses(op,f,42,Failure::Identity,false);
 }
 MotionFake f(k1());Operations op;std::string e;COUNT(op.bind(k1().sha256,f.base,&f,e));
 f.unmap(f.crate,4);refuses(op,f,42,Failure::Identity,false);
}

void id_roundtrip_mismatch_refuses() {
 MotionFake f(k1());Operations op;std::string e;COUNT(op.bind(k1().sha256,f.base,&f,e));
 f.put<std::uint32_t>(f.crate+k1().id,43);refuses(op,f,42,Failure::Identity,false);
}

void capture_reads_server_xyz_and_orientation() {
 const Profile& p=k1();MotionFake f(p);Operations op;std::string e;COUNT(op.bind(p.sha256,f.base,&f,e));
 Capture c;COUNT(op.capture(42,c,e));COUNT(op.last_failure()==Failure::None);COUNT(f.calls==1);
 COUNT(c.id==42&&c.object==f.crate&&c.epoch==op.epoch()&&c.area_id==0x7f000123);
 COUNT(c.position[0]==1.5f&&c.position[1]==-2.25f&&c.position[2]==0.125f);
 COUNT(c.orientation[0]==0.f&&c.orientation[1]==1.f&&c.orientation[2]==0.f);
 COUNT(std::fabs(c.facing-90.f)<1e-4f);
 COUNT(c.push_gate_raw==1&&!c.dirty_position&&!c.dirty_orientation&&c.collision_registered);
 COUNT(c.quaternion_raw[0]==1.f&&c.quaternion_raw[1]==0.f&&c.quaternion_raw[2]==0.f&&c.quaternion_raw[3]==0.f);
 // Dirty word: only bits 1 and 2 are exposed; bit 0 (animation) is not.
 f.put<std::uint32_t>(f.crate+p.dirty,1);COUNT(op.capture(42,c,e));COUNT(!c.dirty_position&&!c.dirty_orientation);
 f.put<std::uint32_t>(f.crate+p.dirty,2);COUNT(op.capture(42,c,e));COUNT(c.dirty_position&&!c.dirty_orientation);
 f.put<std::uint32_t>(f.crate+p.dirty,4);COUNT(op.capture(42,c,e));COUNT(!c.dirty_position&&c.dirty_orientation);
 f.put<std::uint32_t>(f.crate+p.dirty,0xffffffff);COUNT(op.capture(42,c,e));COUNT(c.dirty_position&&c.dirty_orientation);
 // Push gate is raw; any value passes through untouched.
 f.put<std::uint32_t>(f.crate+p.push_gate,0);COUNT(op.capture(42,c,e));COUNT(c.push_gate_raw==0);
 f.put<std::uint32_t>(f.crate+p.push_gate,0xdeadbeef);COUNT(op.capture(42,c,e));COUNT(c.push_gate_raw==0xdeadbeef);
 // AABB marker: >=0 registered, -1 none; never exposed as a number.
 f.put<std::int32_t>(f.crate+p.aabb_marker,-1);COUNT(op.capture(42,c,e));COUNT(!c.collision_registered);
 f.put<std::int32_t>(f.crate+p.aabb_marker,0);COUNT(op.capture(42,c,e));COUNT(c.collision_registered);
 // Facing: atan2(y,x) in degrees, normalised to [0,360).
 f.put(f.crate+p.orientation,-1.f);f.put(f.crate+p.orientation+4,0.f);COUNT(op.capture(42,c,e));COUNT(std::fabs(c.facing-180.f)<1e-4f);
 f.put(f.crate+p.orientation,0.f);f.put(f.crate+p.orientation+4,-1.f);COUNT(op.capture(42,c,e));COUNT(std::fabs(c.facing-270.f)<1e-4f);
 f.put(f.crate+p.orientation,1.f);f.put(f.crate+p.orientation+4,0.f);COUNT(op.capture(42,c,e));COUNT(c.facing==0.f);
 // Tiny negative angle: 360 - 5.7e-6 rounds to 360.0f unless wrapped after the cast.
 f.put(f.crate+p.orientation+4,-1e-7f);COUNT(op.capture(42,c,e));COUNT(c.facing>=0.f&&c.facing<360.f);
 // Quaternion raw order is passed through exactly as stored.
 // Exactly representable values: -m32 x87 may widen float literals.
 f.put(f.crate+p.quaternion,.125f);f.put(f.crate+p.quaternion+4,-.25f);f.put(f.crate+p.quaternion+8,.5f);f.put(f.crate+p.quaternion+12,.75f);
 COUNT(op.capture(42,c,e));COUNT(c.quaternion_raw[0]==.125f&&c.quaternion_raw[1]==-.25f&&c.quaternion_raw[2]==.5f&&c.quaternion_raw[3]==.75f);
 COUNT(f.calls==14); // one getter call per capture, 14 captures above
}

void nonfinite_value_refuses() {
 const Profile& p=k1();
 for(unsigned field:{p.position,p.position+4,p.position+8,p.orientation,p.orientation+8,p.quaternion,p.quaternion+12})
  for(float bad:{std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::infinity(),-std::numeric_limits<float>::infinity()}) {
   MotionFake f(p);Operations op;std::string e;COUNT(op.bind(p.sha256,f.base,&f,e));
   f.put(f.crate+field,bad);refuses(op,f,42,Failure::Value,false);
  }
}

void unreadable_field_refuses() {
 const Profile& p=k1();
 for(unsigned field:{p.area_id,p.position+8,p.orientation+4,p.push_gate,p.dirty,p.aabb_marker,p.quaternion+12,p.type,p.id}) {
  MotionFake f(p);Operations op;std::string e;COUNT(op.bind(p.sha256,f.base,&f,e));
  f.unmap(f.crate+field,1);
  Capture c;COUNT(!op.capture(42,c,e));COUNT(untouched(c));
  COUNT(op.last_failure()==Failure::Identity||op.last_failure()==Failure::Chain);
 }
}

void accepts_client_id_0xffffffff() {
 // Only OBJECT_INVALID (0x7f000000) is refused before the call. 0x7fffffff and
 // 0xffffffff are valid uint32 inputs and must reach the engine getter.
 for(std::uint32_t id:{0xffffffffu,0x7fffffffu,0x80000001u,0u}) {
  MotionFake f(k1());Operations op;std::string e;COUNT(op.bind(k1().sha256,f.base,&f,e));
  f.placeable(0x1008000,id);
  Capture c;COUNT(op.capture(id,c,e));COUNT(c.id==id&&c.object==0x1008000);
  COUNT(f.calls==1&&f.ids.back()==id);
 }
}

void unbind_bumps_epoch() {
 MotionFake f(k1());Operations op;std::string e;COUNT(op.bind(k1().sha256,f.base,&f,e));
 Capture a;COUNT(op.capture(42,a,e));auto first=a.epoch;
 op.unbind();refuses(op,f,42,Failure::Unsupported,true);
 COUNT(op.bind(k1().sha256,f.base,&f,e));Capture b;COUNT(op.capture(42,b,e));COUNT(b.epoch>first);
}

// --- Lua --------------------------------------------------------------------
int forged(lua_State* L) {
 auto size=lua_objlen(L,1);void* memory=lua_newuserdata(L,size);std::memset(memory,0,size);
 lua_getmetatable(L,1);lua_setmetatable(L,-2);return 1;
}
void run_lua(MotionFake& f,const char* program){
 lua_State* L=luaL_newstate();luaL_openlibs(L);register_all(L);
 lua_pushcfunction(L,forged);lua_setglobal(L,"fake_capture");
 lua_pushlightuserdata(L,&f);
 lua_pushcclosure(L,[](lua_State* S)->int{
  lua_pushnumber(S,static_cast<MotionFake*>(lua_touserdata(S,lua_upvalueindex(1)))->calls);return 1;},1);
 lua_setglobal(L,"getter_calls");
 int rc=luaL_dostring(L,program);
 std::string err=rc?lua_tostring(L,-1):"";
 lua_close(L);
 if(rc)throw std::runtime_error("lua: "+err);
 ++checks;
}

void lua_unbound_capabilities_false() {
 operations().unbind();MotionFake f(k1());
 run_lua(f,R"(
  local caps=assert(kp.motion.capabilities())
  assert(caps.available==false and caps.profile=="unsupported" and caps.writes==false)
  local c,err=kp.motion.capture(42)
  assert(c==nil and err:find("^unsupported"))
  assert(getter_calls()==0)
 )");
}

void forged_userdata_argerror() {
 MotionFake f(k1());std::string e;CHECK(operations().bind(k1().sha256,f.base,&f,e));
 run_lua(f,R"(
  local c=assert(kp.motion.capture(42))
  assert(type(c)=="userdata" and getmetatable(c)=="protected motion capture")
  local proxy=newproxy(true);debug.setmetatable(proxy,debug.getmetatable(c))
  assert(not pcall(function()return proxy.id end))
  local fake=fake_capture(c)
  local ok,err=pcall(function()return fake.id end)
  assert(not ok and tostring(err):find("magic"))
  assert(not pcall(function()c.id=7 end))
  assert(not pcall(setmetatable,c,{}))
 )");
 operations().unbind();
}

void lua_capture_surface() {
 MotionFake f(k1());std::string e;CHECK(operations().bind(k1().sha256,f.base,&f,e));
 f.put<std::uint32_t>(f.crate+k1().dirty,2);
 run_lua(f,R"(
  local caps=kp.motion.capabilities()
  assert(caps.available==true and caps.profile=="windows-k1-gog" and caps.writes==false)
  assert(caps.abi=="windows-i386-thiscall" and type(caps.limits)=="string")
  -- No write API in M1, and no NWScript-shaped aliases.
  for _,n in ipairs{"relocate","restore","observe","SetPosition","GetPosition","SetFacing","GetFacing","JumpToLocation"} do
   assert(kp.motion[n]==nil,n)
  end
  local keys={} for k in pairs(kp.motion) do keys[#keys+1]=k end table.sort(keys)
  assert(table.concat(keys,",")=="capabilities,capture",table.concat(keys,","))
  -- Exact uint32 ids only; refused before the engine call.
  local bad={1.5,-1,4294967296,0/0,1/0,-1/0,"42",{},true}
  for i=1,#bad do
   local c,err=kp.motion.capture(bad[i])
   assert(c==nil and err:find("^value"),tostring(bad[i]))
  end
  local c0,e0=kp.motion.capture() assert(c0==nil and e0:find("^value"))
  assert(getter_calls()==0)
  local c=assert(kp.motion.capture(42))
  assert(getter_calls()==1)
  assert(c.id==42 and c.area_id==0x7f000123 and c.object=="0x1004000")
  local p=c.position assert(p.x==1.5 and p.y==-2.25 and p.z==0.125)
  local o=c.orientation assert(o.x==0 and o.y==1 and o.z==0)
  assert(math.abs(c.facing-90)<1e-4)
  assert(c.push_gate_raw==1 and c.dirty_position==true and c.dirty_orientation==false)
  assert(c.collision_registered==true)
  local q=c.quaternion_raw assert(#q==4 and q[1]==1 and q[2]==0 and q[3]==0 and q[4]==0)
  assert(c.quaternion_order=="unverified")
  assert(type(c.epoch)=="number")
  assert(c.aabb_marker==nil and c.dirty==nil and c.bogus==nil)
  -- Tables are copies; editing one does not change the capture.
  p.x=99 assert(c.position.x==1.5)
  local none,err=kp.motion.capture(77)
  assert(none==nil and err:find("^identity"))
 )");
 f.put<std::uint8_t>(f.crate+k1().type,5);
 run_lua(f,R"(
  local c,err=kp.motion.capture(42)
  assert(c==nil and err:find("^identity"))
 )");
 operations().unbind();
}

// --- data cross-checks --------------------------------------------------------
std::string slurp(const std::string& path){std::ifstream in(path,std::ios::binary);std::stringstream s;s<<in.rdbuf();return s.str();}
// Minimal reader for one flat object in the generated table: "name": { ... }.
bool row(const std::string& json,const std::string& name,std::string& body){
 auto at=json.find("\""+name+"\": {");if(at==std::string::npos)return false;
 auto end=json.find('}',at);body=json.substr(at,end-at);return true;
}
std::string text_field(const std::string& body,const std::string& key){
 auto at=body.find("\""+key+"\": \"");if(at==std::string::npos)return "";
 at+=key.size()+5;return body.substr(at,body.find('"',at)-at);
}
long num_field(const std::string& body,const std::string& key){
 auto at=body.find("\""+key+"\": ");if(at==std::string::npos)return -1;
 return std::strtol(body.c_str()+at+key.size()+4,nullptr,10);
}
std::string hex8(Address v){char b[16];std::snprintf(b,sizeof b,"0x%08llX",static_cast<unsigned long long>(v));return b;}
const char* span_hex(Address va){for(const auto& s:k1().spans)if(s.va==va)return s.hex;return nullptr;}

void profile_matches_address_table_row() {
 const Profile& p=k1();
 std::string json=slurp(source_root+"/data/addresses/k1_gog_103.json");
 COUNT(!json.empty());
 COUNT(json.find(p.sha256)!=std::string::npos);
 std::string b;
 // Existing rows: strict.
 COUNT(row(json,"server_object.set_position",b));
 COUNT(text_field(b,"addr_hex")=="0x004CD1A0");
 COUNT(span_hex(0x4cd1a0)&&text_field(b,"expected_bytes")==span_hex(0x4cd1a0));
 COUNT(row(json,"object.id",b));COUNT(num_field(b,"offset")==long(p.id)&&num_field(b,"size")==4);
 COUNT(row(json,"object.type",b));COUNT(num_field(b,"offset")==long(p.type)&&num_field(b,"size")==1);
 COUNT(row(json,"g.app_manager",b));COUNT(text_field(b,"addr_hex")==hex8(p.manager_slot));
 COUNT(row(json,"event.placeable",b));
 Address handler=0;for(const auto& s:p.slots)if(s.va==p.placeable_vtable+0x78)handler=s.target;
 COUNT(handler&&text_field(b,"addr_hex")==hex8(handler));
 // Motion rows: must match if the orchestrator has regenerated; else pending.
 struct Want{const char* name;long offset;long size;};
 const Want fields[]={{"server_object.area_id",long(p.area_id),4},{"server_object.position",long(p.position),12},
  {"server_object.orientation",long(p.orientation),12},{"server_object.client_push_gate_unverified",long(p.push_gate),4},
  {"server_object.dirty_bits",long(p.dirty),4},{"placeable.aabb_registered",long(p.aabb_marker),4},
  {"placeable.quaternion_raw_order_unverified",long(p.quaternion),16}};
 std::vector<std::string> pending;
 for(const auto& w:fields) {
  if(!row(json,w.name,b)){pending.push_back(w.name);continue;}
  COUNT(num_field(b,"offset")==w.offset&&num_field(b,"size")==w.size);
 }
 if(row(json,"server.get_placeable_by_object_id",b)) {
  COUNT(text_field(b,"addr_hex")==hex8(p.get_placeable));COUNT(text_field(b,"expected_bytes")==span_hex(p.get_placeable));
 } else pending.push_back("server.get_placeable_by_object_id (proposed row)");
 if(row(json,"placeable.vtable",b)) COUNT(text_field(b,"addr_hex")==hex8(p.placeable_vtable));
 else pending.push_back("placeable.vtable (proposed row)");
 for(const auto& n:pending)std::cout<<"  PENDING regeneration: "<<n<<"\n";
}

// The C++ profile and data/adjudication/k1_gog_103_motion_bindings.json must
// agree on every guard, slot, field offset/size, the getter and the vtable.
void bindings_json_matches_profile() {
 const Profile& p=k1();
 std::string json=slurp(source_root+"/data/adjudication/k1_gog_103_motion_bindings.json");
 COUNT(!json.empty());COUNT(json.find(p.sha256)!=std::string::npos);
 auto section=[&](const char* key,const char* next){
  auto a=json.find(std::string("\"")+key+"\": [");auto b=json.find(std::string("\"")+next+"\": [");
  CHECK(a!=std::string::npos&&b!=std::string::npos&&a<b);return json.substr(a,b-a);};
 auto hexnum=[](const std::string& t){return static_cast<Address>(std::strtoull(t.c_str(),nullptr,16));};
 // Guards: same count, same order, same bytes.
 std::string g=section("guards","slots");std::size_t at=0;unsigned n=0;
 for(const auto& s:p.spans) {
  if(!s.va)continue;
  at=g.find("\"va\": \"",at);COUNT(at!=std::string::npos);
  std::string body=g.substr(at,g.find('}',at)-at);
  COUNT(hexnum(text_field(body,"va"))==s.va);COUNT(text_field(body,"bytes")==s.hex);
  ++at;++n;
 }
 COUNT(g.find("\"va\": \"",at)==std::string::npos);COUNT(n==23);
 std::string sl=section("slots","bindings");at=0;
 for(const auto& s:p.slots) {
  at=sl.find("\"va\": \"",at);COUNT(at!=std::string::npos);
  std::string body=sl.substr(at,sl.find('}',at)-at);
  COUNT(hexnum(text_field(body,"va"))==s.va);COUNT(hexnum(text_field(body,"target"))==s.target);++at;
 }
 COUNT(sl.find("\"va\": \"",at)==std::string::npos);
 auto binding=[&](const std::string& name){
  auto a=json.find("\"name\": \""+name+"\"");CHECK(a!=std::string::npos);
  return json.substr(a,json.find("\"evidence\"",a)-a);};
 struct F{const char* name;unsigned offset;long size;};
 const F fields[]={{"CSWSObject::area_id",p.area_id,4},{"CSWSObject::position",p.position,12},
  {"CSWSObject::orientation",p.orientation,12},{"CSWSObject::client_push_gate_unverified",p.push_gate,4},
  {"CSWSObject::dirty_bits",p.dirty,4},{"CSWSPlaceable::aabb_registered",p.aabb_marker,4},
  {"CSWSPlaceable::quaternion_raw_order_unverified",p.quaternion,16}};
 for(const auto& f:fields) {
  std::string b=binding(f.name);
  COUNT(hexnum(text_field(b,"offset"))==f.offset);COUNT(num_field(b,"size")==f.size);
  COUNT(text_field(b,"verdict")=="accept");
 }
 COUNT(hexnum(text_field(binding("CServerExoApp::GetPlaceableByGameObjectID"),"addr"))==p.get_placeable);
 COUNT(hexnum(text_field(binding("CSWSPlaceable::vtable"),"addr"))==p.placeable_vtable);
}

void spans_match_reference_image() {
 const char* env=std::getenv("KP_K1_GOG_IMAGE");const char* home=std::getenv("HOME");
 std::string path=env?env:(home?std::string(home):"")+"/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image";
 std::string image=slurp(path);
 if(image.empty()){std::cout<<"  SKIP reference image absent: "<<path<<"\n";return;}
 const Profile& p=k1();
 auto byte_at=[&](Address va)->int{Address o=va-p.preferred_base;return o<image.size()?static_cast<unsigned char>(image[o]):-1;};
 for(const auto& s:p.spans) {
  if(!s.va)continue;
  auto digit=[](char c){return c<='9'?c-'0':c-'a'+10;};
  for(std::size_t j=0;j*2<std::strlen(s.hex);++j)COUNT(byte_at(s.va+j)==((digit(s.hex[j*2])<<4)|digit(s.hex[j*2+1])));
 }
 for(const auto& s:p.slots) {
  std::uint32_t v=0;for(unsigned j=0;j<4;++j){int c=byte_at(s.va+j);COUNT(c>=0);v|=std::uint32_t(c)<<(8*j);}
  COUNT(v==s.target);
 }
}
} // namespace

int main(int argc,char** argv) {
 if(argc>1)source_root=argv[1];
 struct T{const char* name;void(*fn)();};
 const T tests[]={
  {"motion.unsupported_profile_capabilities_false",unsupported_profile_capabilities_false},
  {"motion.relocated_image_refused",relocated_image_refused},
  {"motion.span_table_valid",span_table_valid},
  {"motion.guard_flip_refuses_before_call",guard_flip_refuses_before_call},
  {"motion.chain_failure_refuses_before_call",chain_failure_refuses_before_call},
  {"motion.invalid_object_id_refused_before_call",invalid_object_id_refused_before_call},
  {"motion.non_placeable_type_refuses",non_placeable_type_refuses},
  {"motion.wrong_vtable_refuses",wrong_vtable_refuses},
  {"motion.id_roundtrip_mismatch_refuses",id_roundtrip_mismatch_refuses},
  {"motion.capture_reads_server_xyz_and_orientation",capture_reads_server_xyz_and_orientation},
  {"motion.nonfinite_value_refuses",nonfinite_value_refuses},
  {"motion.unreadable_field_refuses",unreadable_field_refuses},
  {"motion.accepts_client_id_0xffffffff",accepts_client_id_0xffffffff},
  {"motion.unbind_bumps_epoch",unbind_bumps_epoch},
  {"motion.lua_unbound_capabilities_false",lua_unbound_capabilities_false},
  {"motion.forged_userdata_argerror",forged_userdata_argerror},
  {"motion.lua_capture_surface",lua_capture_surface},
  {"motion.profile_matches_address_table_row",profile_matches_address_table_row},
  {"motion.bindings_json_matches_profile",bindings_json_matches_profile},
  {"motion.spans_match_reference_image",spans_match_reference_image},
 };
 unsigned failed=0;
 for(const auto& t:tests) {
  try{t.fn();std::cout<<"PASS "<<t.name<<"\n";}
  catch(const std::exception& e){++failed;std::cout<<"FAIL "<<t.name<<": "<<e.what()<<"\n";}
  operations().unbind();
 }
 std::cout<<(sizeof(tests)/sizeof(tests[0])-failed)<<"/"<<sizeof(tests)/sizeof(tests[0])<<" tests passed, "
          <<checks<<" checks (synthetic memory; no live ABI proof)\n";
 return failed?1:0;
}
