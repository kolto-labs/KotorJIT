// kp.motion offline tests. M1: profile gating, exact guards, the server
// lookup chain, placeable fences, value checks, the protected Lua surface and
// a read-only cross-check against data/addresses/k1_gog_103.json. M2: the
// engine-thread gate, relocate / restore / observe, the ownership ledger and
// refusal rules R1..R12 from motion-m2-plan.md section 4.
// Synthetic memory only; this proves nothing about the live game.
// Usage: kp_motiontest [source-root]
#include "api/motion.hpp"
#include "api/engine_gate.hpp"
#include <algorithm>
#include <cctype>
#include <filesystem>
#include <set>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <functional>
#include <iterator>
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
namespace engine=kp::api::engine;
#define CHECK(x) do{if(!(x))throw std::runtime_error(std::string("line ")+std::to_string(__LINE__)+": "+#x);}while(0)

namespace {
unsigned checks=0;
#define COUNT(x) do{CHECK(x);++checks;}while(0)
const Profile& k1(){return profiles().front();}
std::string source_root=".";
// The engine-thread gate. main() binds it open for every test; a test that
// needs it shut flips gate_open or unbinds it, and main() rebinds after.
bool gate_open=true;
bool gate_probe(void* c){return *static_cast<bool*>(c);}
void open_gate(){gate_open=true;engine::bind_gate(gate_probe,&gate_open);}

// Sparse synthetic memory. Only mapped bytes are readable. The typed getter is
// modelled as a lookup table and counts every call so a test can prove that a
// refusal happened before the engine was reached.
struct MotionFake:Backend {
 const Profile& p;std::map<Address,unsigned char> bytes;
 Address base;
 Address manager=0x1000000,server=0x1001000,internal=0x1002000,array=0x1003000,crate=0x1004000;
 std::map<std::uint32_t,Address> objects;
 unsigned calls=0;std::vector<std::uint32_t> ids;
 mutable unsigned reads=0;
 // SetPosition model: exactly the engine's 0x4CD1A0 as far as M0 shows it.
 // Early return on 0x4AA980 equality; copy the 3 floats to +0x90; a4==0
 // sets dirty bit value 2. Faults can be injected for the readback tests.
 struct SetCall{Address function,object;std::array<float,3> pos;std::int32_t a2,a3,a4;};
 std::vector<SetCall> sets;
 bool skip_write=false,skip_dirty=false,nudge=false,change_area=false;
 // F2 (motion-m2-review.md): flip the sign of any zero component actually
 // landed, without changing its magnitude. engine_equal folds +0.0/-0.0
 // together (matching the real 0x4AA980 fcomp); bit_equal, used by every
 // fence and the readback contract, must not.
 bool flip_sign=false;
 // F2 (round 2): make a landed position NaN, to prove the readback contract
 // never reaches its bit_equal(after.position, target) fence with a NaN
 // operand -- read_fields's own finite check intercepts first.
 bool write_nan=false;
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
  ++reads;
  auto* b=static_cast<unsigned char*>(out);
  for(std::size_t i=0;i<n;++i){auto it=bytes.find(a+i);if(it==bytes.end())return false;b[i]=it->second;}
  return true;
 }
 Address placeable(Address f,Address s,std::uint32_t id)override{
  CHECK(f==p.get_placeable);CHECK(s==server);++calls;ids.push_back(id);
  auto it=objects.find(id);return it==objects.end()?0:it->second;
 }
 template<class T>T get(Address a)const{T v{};auto* b=reinterpret_cast<unsigned char*>(&v);for(unsigned i=0;i<sizeof v;++i)b[i]=bytes.at(a+i);return v;}
 std::array<float,3> pos(Address o)const{return {get<float>(o+p.position),get<float>(o+p.position+4),get<float>(o+p.position+8)};}
 void set_pos(Address o,float x,float y,float z){put(o+p.position,x);put(o+p.position+4,y);put(o+p.position+8,z);}
 void set_position(Address f,Address o,const std::array<float,3>& v,std::int32_t a2,std::int32_t a3,std::int32_t a4)override{
  sets.push_back({f,o,v,a2,a3,a4});
  if(engine_equal(pos(o),v))return;
  if(!skip_write){
   std::array<float,3> w=v;
   if(nudge){std::uint32_t bits;std::memcpy(&bits,&w[0],4);++bits;std::memcpy(&w[0],&bits,4);}
   if(flip_sign)for(float& c:w)if(c==0.f){std::uint32_t bits;std::memcpy(&bits,&c,4);bits^=0x80000000u;std::memcpy(&c,&bits,4);}
   if(write_nan)w[0]=std::numeric_limits<float>::quiet_NaN();
   set_pos(o,w[0],w[1],w[2]);
  }
  if(a4==0&&!skip_dirty)put<std::uint32_t>(o+p.dirty,get<std::uint32_t>(o+p.dirty)|2u);
  if(change_area)put<std::uint32_t>(o+p.area_id,0x7f000999);
 }
};

bool untouched(const Capture& c){
 Capture d;
 return c.epoch==d.epoch && c.id==d.id && c.object==d.object && c.area_id==d.area_id && c.position==d.position &&
        c.orientation==d.orientation && c.facing==d.facing && c.push_gate_raw==d.push_gate_raw &&
        c.dirty_position==d.dirty_position && c.dirty_orientation==d.dirty_orientation &&
        c.collision_registered==d.collision_registered && c.quaternion_raw==d.quaternion_raw && c.owned==d.owned;
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
 COUNT(n==28);
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
  assert(caps.available==false and caps.profile=="unsupported")
  assert(type(caps.writes)=="table" and #caps.writes==0)
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
  assert(caps.available==true and caps.profile=="windows-k1-gog")
  assert(type(caps.writes)=="table" and #caps.writes==1 and caps.writes[1]=="position")
  assert(caps.abi=="windows-i386-thiscall" and type(caps.limits)=="string")
  -- No NWScript-shaped aliases.
  for _,n in ipairs{"SetPosition","GetPosition","SetFacing","GetFacing","JumpToLocation","SetOrientation"} do
   assert(kp.motion[n]==nil,n)
  end
  local keys={} for k in pairs(kp.motion) do keys[#keys+1]=k end table.sort(keys)
  assert(table.concat(keys,",")=="capabilities,capture,observe,relocate,restore",table.concat(keys,","))
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
 COUNT(g.find("\"va\": \"",at)==std::string::npos);COUNT(n==28);
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
 // M2: the setter binding, two derivations, same VA as the profile.
 std::string set=binding("CSWSObject::SetPosition");
 COUNT(hexnum(text_field(set,"addr"))==p.set_position);COUNT(text_field(set,"verdict")=="accept");
 auto whole=json.find("\"name\": \"CSWSObject::SetPosition\"");
 std::string row=json.substr(whole,json.find("\"name\": \"",whole+1)-whole);
 COUNT(row.find("\"M0 receipt\"")!=std::string::npos&&row.find("\"independent verification\"")!=std::string::npos);
 COUNT(row.find("538b5c240856578bf18dbe9000000053 @0x4cd1a0")!=std::string::npos);
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
// --- M2: relocate / restore / observe (motion-m2-plan.md sections 1-5) --------
constexpr std::uint64_t T1=101,T2=202;
const float qnan=std::numeric_limits<float>::quiet_NaN();
// Crate 42 in the fake: position (1.5,-2.25,0.125), area 0x7f000123, walkmesh
// registered (marker 3). Write tests clear the marker unless they test R8.
struct Rig{
 MotionFake f;Operations op;std::string e;
 explicit Rig(bool collision=false):f(k1()){CHECK(op.bind(k1().sha256,f.base,&f,e));if(!collision)f.put<std::int32_t>(f.crate+k1().aabb_marker,-1);}
 Capture cap(std::uint32_t id=42){Capture c;CHECK(op.capture(id,c,e));return c;}
 bool move(std::uint64_t t,const Capture& c,std::array<float,3> to,Capture& out,Status& st,bool allow=false,Writer w=Writer::Loaded){
  return op.relocate(t,w,c,to,allow,out,st,e);}
 // Relocate that must succeed; returns the post-readback capture.
 Capture moved(std::uint64_t t,const Capture& c,std::array<float,3> to,bool allow=false){
  Capture out;Status st=Status::Noop;
  if(!move(t,c,to,out,st,allow))throw std::runtime_error("relocate failed: "+e);
  CHECK(st==Status::Moved);return out;}
 struct Counters{unsigned reads,calls,sets;};
 Counters snap()const{return {f.reads,f.calls,unsigned(f.sets.size())};}
};
std::array<float,3> v3(float x,float y,float z){return {x,y,z};}
bool is(const Rig& r,Failure f,const char* text=nullptr){
 return r.op.last_failure()==f&&r.e.rfind(std::string(failure_name(f))+":",0)==0&&(!text||r.e.find(text)!=std::string::npos);}
// A refused write: the kind, no setter call, no ledger change, output untouched.
void refused_write(Rig& r,std::uint64_t t,const Capture& c,std::array<float,3> to,Failure kind,const char* text=nullptr,
                   bool allow=false,Writer w=Writer::Loaded){
 auto before=r.snap();std::size_t ledger=r.op.ledger_size();std::uint64_t owner=r.op.owner_of(c.id);
 Capture out;Status st=Status::Moved;
 COUNT(!r.move(t,c,to,out,st,allow,w));
 if(!is(r,kind,text))throw std::runtime_error("expected "+std::string(failure_name(kind))+(text?std::string(" /")+text:"")+", got: "+r.e);
 COUNT(r.f.sets.size()==before.sets);COUNT(r.op.ledger_size()==ledger);COUNT(r.op.owner_of(c.id)==owner);
 COUNT(untouched(out));COUNT(st==Status::Moved);
}

void gate_refusal_zero_reads_zero_calls(){
 Rig r;Capture c=r.cap();
 Capture m=r.moved(T1,c,v3(2.5f,-2.25f,.125f));   // an entry to restore/observe
 for(int mode=0;mode<2;++mode){
  if(mode==0)gate_open=false;else engine::bind_gate(nullptr,nullptr);   // closed, then unbound
  auto before=r.snap();Capture out;Observation o;std::string e;Status st=Status::Moved;
  const std::string want="unsupported: not on the engine thread";
  COUNT(!r.op.capture(42,out,e));COUNT(e==want);COUNT(untouched(out));
  COUNT(!r.op.relocate(T1,Writer::Loaded,m,v3(3.f,-2.25f,.125f),false,out,st,e));COUNT(e==want);
  COUNT(!r.op.relocate(T1,Writer::Loaded,m,v3(qnan,0,0),false,out,st,e));COUNT(e==want);   // gate before args
  COUNT(!r.op.relocate(0,Writer::None,m,v3(3.f,-2.25f,.125f),false,out,st,e));COUNT(e==want);   // gate before R3
  COUNT(!r.op.restore(T1,Writer::Loaded,42,out,e));COUNT(e==want);
  COUNT(!r.op.observe(42,m.object,o,e));COUNT(e==want);
  auto after=r.snap();
  COUNT(after.reads==before.reads);COUNT(after.calls==before.calls);COUNT(after.sets==before.sets);
  COUNT(r.op.owner_of(42)==T1);   // a refusal never touches the ledger
  COUNT(untouched(out)&&st==Status::Moved);
  open_gate();
 }
 // Unbound profile: unsupported before the gate is even asked; no reads.
 Operations none;Capture out;std::string e;COUNT(!none.capture(42,out,e));COUNT(e.rfind("unsupported",0)==0);
}

void nonfinite_refused_zero_calls(){
 Rig r;Capture c=r.cap();
 for(float bad:{qnan,std::numeric_limits<float>::infinity(),-std::numeric_limits<float>::infinity()})
  for(int axis=0;axis<3;++axis){
   std::array<float,3> t=c.position;t[axis]=bad;
   auto before=r.snap();
   refused_write(r,T1,c,t,Failure::Value,"not finite");
   auto after=r.snap();COUNT(after.reads==before.reads&&after.calls==before.calls);   // R4 precedes every read
  }
}

void step_bound_refused(){
 Rig r;Capture c=r.cap();
 refused_write(r,T1,c,v3(1.5f+5.25f,-2.25f,.125f),Failure::Bounds,"5.0 m");
 refused_write(r,T1,c,v3(1.5f+3.f,-2.25f+4.5f,.125f),Failure::Bounds,"5.0 m");   // 5.41 m diagonal
 refused_write(r,T1,c,v3(2e5f,-2.25f,.125f),Failure::Bounds,"1e5");
 Capture m=r.moved(T1,c,v3(1.5f+5.f,-2.25f,.125f));   // exactly 5.0 m is allowed
 COUNT(m.position[0]==6.5f);
}

void dz_bound_refused(){
 Rig r;Capture c=r.cap();
 refused_write(r,T1,c,v3(1.5f,-2.25f,.125f+1.125f),Failure::Bounds,"1.0 m");
 refused_write(r,T1,c,v3(1.5f,-2.25f,.125f-1.125f),Failure::Bounds,"1.0 m");
 r.moved(T1,c,v3(1.5f,-2.25f,1.125f));   // exactly +1.0 m
}

void origin_range_refused(){
 Rig r;Capture c=r.cap();
 // 4.5 m steps along x from the origin 1.5: 6, 10.5, 15, 19.5, 24 (22.5 m) pass;
 // 28.5 is 27 m from the origin and is refused although the step is legal.
 for(float x:{6.f,10.5f,15.f,19.5f,24.f})c=r.moved(T1,c,v3(x,-2.25f,.125f));
 refused_write(r,T1,c,v3(28.5f,-2.25f,.125f),Failure::Bounds,"origin");
 const Entry* e=r.op.entry(42);COUNT(e&&e->origin_position==v3(1.5f,-2.25f,.125f)&&e->writes==5);
}

void stale_capture_pose_refused(){
 Rig r;Capture c=r.cap();
 r.f.set_pos(r.f.crate,1.5f,-2.25f,.25f);   // someone else moved it after the capture
 refused_write(r,T1,c,v3(2.f,-2.25f,.25f),Failure::Stale,"pose changed");
 Capture fresh=r.cap();r.f.put(r.f.crate+k1().orientation,1.f);   // orientation changed
 refused_write(r,T1,fresh,v3(2.f,-2.25f,.25f),Failure::Stale,"pose changed");
 // A capture2 from a successful relocate is the one the next call needs.
 Capture a=r.cap();Capture b=r.moved(T1,a,v3(2.5f,-2.25f,.25f));
 refused_write(r,T1,a,v3(3.f,-2.25f,.25f),Failure::Stale,"pose changed");
 r.moved(T1,b,v3(3.f,-2.25f,.25f));
}

// F2: motion.cpp's R6 stale-pose check (`bit_equal(cur.position,
// from.position)`) must catch a sign-only flip on a zero component, which
// engine_equal would call the same pose. Kills the `stale` mutant
// (bit_equal -> engine_equal at that site).
void stale_capture_pose_refused_on_signed_zero(){
 Rig r;r.f.set_pos(r.f.crate,1.5f,-2.25f,0.f);
 Capture c=r.cap();
 r.f.set_pos(r.f.crate,1.5f,-2.25f,-0.f);   // another writer flips the sign only
 COUNT(engine_equal(c.position,r.f.pos(r.f.crate)));
 COUNT(!bit_equal(c.position,r.f.pos(r.f.crate)));
 refused_write(r,T1,c,v3(2.f,-2.25f,0.f),Failure::Stale,"pose changed");
}

// F2 (round 2): a NaN cannot reach R6's bit_equal/engine_equal choice at all
// -- locate()/read_fields() (motion.cpp:161) refuses non-finite fields
// itself, before line 224 is ever reached. So the refusal kind here is
// Value, not Stale: proof the fence is unreachable with a NaN operand,
// which is why no NaN-payload variant of stale_capture_pose_refused exists
// (bit_equal and engine_equal cannot disagree on a case neither ever sees).
void stale_capture_refused_on_nan_before_fence(){
 Rig r;Capture c=r.cap();
 r.f.set_pos(r.f.crate,qnan,-2.25f,.125f);   // corrupted since the capture
 refused_write(r,T1,c,v3(2.f,-2.25f,.125f),Failure::Value,"not finite");
}

void stale_epoch_refused(){
 Rig r;Capture c=r.cap();
 r.op.unbind();CHECK(r.op.bind(k1().sha256,r.f.base,&r.f,r.e));
 auto before=r.snap();
 refused_write(r,T1,c,v3(2.f,-2.25f,.125f),Failure::Stale,"earlier motion binding");
 COUNT(r.snap().calls==before.calls);   // no getter call: the epoch needs no read
 Capture forged;forged.epoch=r.op.epoch();forged.id=42;   // object 0: never captured
 refused_write(r,T1,forged,v3(2.f,-2.25f,.125f),Failure::Stale);
}

void area_change_refused(){
 Rig r;Capture c=r.cap();
 r.f.put<std::uint32_t>(r.f.crate+k1().area_id,0x7f000124);
 refused_write(r,T1,c,v3(2.f,-2.25f,.125f),Failure::Stale,"area changed");
}

void area_sentinel_refused(){
 for(std::uint32_t area:{0x7f000000u,0u}){
  Rig r;r.f.put<std::uint32_t>(r.f.crate+k1().area_id,area);
  Capture c=r.cap();   // capture reads it; only a write is refused
  refused_write(r,T1,c,v3(2.f,-2.25f,.125f),Failure::Stale,"not in an area");
 }
}

void collision_registered_refused_by_default(){
 for(std::int32_t marker:{3,0}){
  Rig r(true);r.f.put<std::int32_t>(r.f.crate+k1().aabb_marker,marker);
  Capture c=r.cap();COUNT(c.collision_registered);
  refused_write(r,T1,c,v3(2.f,-2.25f,.125f),Failure::Collision,"walkmesh");
 }
}

void collision_opt_in_allows(){
 Rig r(true);Capture c=r.cap();COUNT(c.collision_registered);
 Capture m=r.moved(T1,c,v3(2.f,-2.25f,.125f),true);
 COUNT(m.position==v3(2.f,-2.25f,.125f));COUNT(m.collision_registered);   // the marker is untouched
 COUNT(r.f.get<std::int32_t>(r.f.crate+k1().aabb_marker)==3);
 // The opt-in is per call: the next call without it is refused again.
 refused_write(r,T1,m,v3(2.5f,-2.25f,.125f),Failure::Collision);
}

void relocate_single_setter_call_flags_110(){
 Rig r;Capture c=r.cap();auto before=r.snap();
 Capture m=r.moved(T1,c,v3(2.f,-1.75f,.5f));
 COUNT(r.f.sets.size()==1);
 const auto& s=r.f.sets.back();
 COUNT(s.function==0x4cd1a0&&s.function==r.op.profile()->set_position);   // at(VA) with the preferred base
 COUNT(s.object==r.f.crate);COUNT(s.pos==v3(2.f,-1.75f,.5f));
 COUNT(s.a2==1&&s.a3==1&&s.a4==0);
 COUNT(r.snap().calls==before.calls+1);   // one getter per relocate; readback uses raw reads
 COUNT(m.owned&&r.op.owner_of(42)==T1);
}

void readback_requires_exact_pos_and_dirty_bit(){
 {Rig r;Capture c=r.cap();Capture m=r.moved(T1,c,v3(2.f,-2.25f,.125f));
  COUNT(bit_equal(m.position,v3(2.f,-2.25f,.125f)));COUNT(m.dirty_position);}
 {Rig r;r.f.skip_dirty=true;Capture c=r.cap();Capture out;Status st;
  COUNT(!r.move(T1,c,v3(2.f,-2.25f,.125f),out,st));COUNT(is(r,Failure::Mutation,"dirty bit"));COUNT(r.f.sets.size()==1);}
 {Rig r;r.f.nudge=true;Capture c=r.cap();Capture out;Status st;
  COUNT(!r.move(T1,c,v3(2.f,-2.25f,.125f),out,st));COUNT(is(r,Failure::Mutation,"readback mismatch"));}
 {Rig r;r.f.skip_write=true;Capture c=r.cap();Capture out;Status st;
  COUNT(!r.move(T1,c,v3(2.f,-2.25f,.125f),out,st));COUNT(is(r,Failure::Mutation,"may have happened"));}
 {Rig r;r.f.change_area=true;Capture c=r.cap();Capture out;Status st;
  COUNT(!r.move(T1,c,v3(2.f,-2.25f,.125f),out,st));COUNT(is(r,Failure::Mutation,"area changed"));}
 // A dirty bit already set before the write still reads as set; the bit is
 // not proof of this write on its own, which is why position is checked too.
}

void readback_mismatch_reports_mutation_and_keeps_entry(){
 Rig r;r.f.nudge=true;Capture c=r.cap();Capture out;Status st=Status::Noop;
 COUNT(!r.move(T1,c,v3(2.f,-2.25f,.125f),out,st));COUNT(is(r,Failure::Mutation));
 const Entry* e=r.op.entry(42);
 COUNT(e&&e->owner_token==T1&&e->writes==1);
 COUNT(e->origin_position==v3(1.5f,-2.25f,.125f));
 COUNT(bit_equal(e->last_written,r.f.pos(r.f.crate)));   // the readback, not the target
 COUNT(!bit_equal(e->last_written,v3(2.f,-2.25f,.125f)));
 // Restore still works from the recorded origin.
 r.f.nudge=false;Capture back;
 COUNT(r.op.restore(T1,Writer::Loaded,42,back,r.e));COUNT(bit_equal(r.f.pos(r.f.crate),v3(1.5f,-2.25f,.125f)));
 COUNT(r.op.entry(42)==nullptr);
}

// F2: the readback contract (`write_and_verify`'s `bit_equal(after.position,
// target)`) must catch a landed position that is engine-equal to the target
// but sign-flipped on a zero component. Kills the `readback` mutant
// (bit_equal -> engine_equal at that site).
void readback_mismatch_on_signed_zero(){
 Rig r;r.f.flip_sign=true;Capture c=r.cap();Capture out;Status st=Status::Noop;
 COUNT(!r.move(T1,c,v3(2.f,-2.25f,0.f),out,st));
 COUNT(is(r,Failure::Mutation,"readback mismatch"));
 COUNT(r.f.sets.size()==1);
 COUNT(engine_equal(r.f.pos(r.f.crate),v3(2.f,-2.25f,0.f)));
 COUNT(!bit_equal(r.f.pos(r.f.crate),v3(2.f,-2.25f,0.f)));
}

// F2 (round 2): if the landed position comes back NaN (a corrupt write, or
// an engine that faults mid-write), write_and_verify's own read_fields call
// (motion.cpp:189) refuses it as a failed readback before line 194's
// bit_equal(after.position, target) is ever evaluated. So this is Mutation
// / "readback failed", not a readback mismatch: proof bit_equal and
// engine_equal cannot disagree here either, since neither ever sees the
// NaN operand.
void readback_refused_on_nan_landed(){
 Rig r;r.f.write_nan=true;Capture c=r.cap();Capture out;Status st=Status::Noop;
 COUNT(!r.move(T1,c,v3(2.f,-2.25f,.125f),out,st));
 COUNT(is(r,Failure::Mutation,"readback failed"));
 COUNT(r.f.sets.size()==1);
}

void same_position_reported_noop_zero_setter_calls(){
 {Rig r;Capture c=r.cap();Capture out;Status st=Status::Moved;auto before=r.snap();
  COUNT(r.move(T1,c,c.position,out,st));COUNT(st==Status::Noop);COUNT(r.f.sets.size()==before.sets);
  COUNT(r.op.ledger_size()==0);COUNT(!out.owned);COUNT(bit_equal(out.position,c.position));}
 // -0.0 against 0.0: the engine's 0x4AA980 fcomp calls them equal and
 // returns early, so the setter must not be called (else a false mutation).
 {Rig r;r.f.set_pos(r.f.crate,1.5f,-2.25f,0.f);Capture c=r.cap();Capture out;Status st=Status::Moved;
  COUNT(r.move(T1,c,v3(1.5f,-2.25f,-0.f),out,st));COUNT(st==Status::Noop);COUNT(r.f.sets.empty());}
 {Rig r;r.f.set_pos(r.f.crate,-0.f,-0.f,-0.f);Capture c=r.cap();Capture out;Status st=Status::Moved;
  COUNT(r.move(T1,c,v3(0.f,0.f,0.f),out,st));COUNT(st==Status::Noop);COUNT(r.f.sets.empty());}
 COUNT(engine_equal(v3(0.f,1.f,2.f),v3(-0.f,1.f,2.f)));COUNT(!bit_equal(v3(0.f,1.f,2.f),v3(-0.f,1.f,2.f)));
 COUNT(!engine_equal(v3(qnan,0,0),v3(qnan,0,0)));   // NaN is never equal, as fcomp
 COUNT(!engine_equal(v3(1.f,0,0),v3(std::nextafter(1.f,2.f),0,0)));
 // The one case the two functions could disagree on: a bit-identical NaN
 // payload on both sides. bit_equal's memcmp says equal; engine_equal's
 // is_nan short-circuit says not-equal regardless. Unreachable at any of
 // the three motion.cpp fences (read_fields validates finiteness upstream
 // of all of them -- see stale_capture_refused_on_nan_before_fence,
 // readback_refused_on_nan_landed, restore_refused_on_nan_before_fence),
 // but the primitives themselves must still be exact about it.
 COUNT(bit_equal(v3(qnan,0,0),v3(qnan,0,0)));
 COUNT(!engine_equal(v3(qnan,0,0),v3(qnan,0,0)));
}

void restore_exact_readback(){
 Rig r;Capture c=r.cap();Capture m=r.moved(T1,c,v3(2.f,-1.75f,.5f));
 m=r.moved(T1,m,v3(3.f,-1.25f,.75f));
 Capture back;COUNT(r.op.restore(T1,Writer::Loaded,42,back,r.e));
 COUNT(bit_equal(back.position,c.position));COUNT(bit_equal(r.f.pos(r.f.crate),c.position));
 COUNT(back.dirty_position);COUNT(!back.owned);
 COUNT(r.f.sets.size()==3);const auto& s=r.f.sets.back();COUNT(s.pos==c.position&&s.a2==1&&s.a3==1&&s.a4==0);
 COUNT(r.op.owner_of(42)==0&&r.op.ledger_size()==0);
 auto before=r.snap();
 COUNT(!r.op.restore(T1,Writer::Loaded,42,back,r.e));COUNT(is(r,Failure::NotOwner));
 COUNT(r.snap().calls==before.calls&&r.snap().sets==before.sets);
 // A capture after restore can be moved again, as a fresh first write.
 r.moved(T2,r.cap(),v3(2.f,-2.25f,.125f));COUNT(r.op.owner_of(42)==T2);
}

void restore_refused_after_identity_change(){
 struct Case{const char* what;Failure kind;std::function<void(Rig&)> breakit;};
 const Profile& p=k1();
 std::vector<Case> cases{
  {"vtable",Failure::Identity,[&](Rig& r){r.f.ptr(r.f.crate,0x745f18);}},
  {"type",Failure::Identity,[&](Rig& r){r.f.put<std::uint8_t>(r.f.crate+p.type,5);}},
  {"id",Failure::Identity,[&](Rig& r){r.f.put<std::uint32_t>(r.f.crate+p.id,43);}},
  {"gone",Failure::Identity,[&](Rig& r){r.f.objects.erase(42);}},
  {"pointer",Failure::Identity,[&](Rig& r){   // id 42 now resolves to a different object at the same pose
   Capture now=r.cap();r.f.placeable(0x1009000,42);r.f.set_pos(0x1009000,now.position[0],now.position[1],now.position[2]);}},
  {"area",Failure::Stale,[&](Rig& r){r.f.put<std::uint32_t>(r.f.crate+p.area_id,0x7f000124);}},
 };
 for(auto& k:cases){
  Rig r;r.moved(T1,r.cap(),v3(2.f,-2.25f,.125f));
  k.breakit(r);auto before=r.snap();Capture out;
  COUNT(!r.op.restore(T1,Writer::Loaded,42,out,r.e));
  if(!is(r,k.kind,"ownership released"))throw std::runtime_error(std::string(k.what)+": "+r.e);
  COUNT(r.snap().sets==before.sets);COUNT(r.op.entry(42)==nullptr);COUNT(untouched(out));
 }
 // Guards and the chain may be transient: refused, but ownership is kept.
 {Rig r;r.moved(T1,r.cap(),v3(2.f,-2.25f,.125f));
  r.f.ptr(r.f.internal+p.internal_array,0);Capture out;
  COUNT(!r.op.restore(T1,Writer::Loaded,42,out,r.e));COUNT(is(r,Failure::Chain));COUNT(r.op.owner_of(42)==T1);
  r.f.ptr(r.f.internal+p.internal_array,r.f.array);COUNT(r.op.restore(T1,Writer::Loaded,42,out,r.e));}
}

void restore_conflict_when_moved_by_other_writer_no_write(){
 {Rig r;r.moved(T1,r.cap(),v3(2.f,-2.25f,.125f));
  r.f.set_pos(r.f.crate,2.25f,-2.25f,.125f);   // NWScript, the engine or a save load moved it
  auto before=r.snap();Capture out;
  COUNT(!r.op.restore(T1,Writer::Loaded,42,out,r.e));COUNT(is(r,Failure::Conflict,"moved by another writer; ownership released"));
  COUNT(r.snap().sets==before.sets);COUNT(r.op.entry(42)==nullptr);
  COUNT(bit_equal(r.f.pos(r.f.crate),v3(2.25f,-2.25f,.125f)));}   // their move survives
 {Rig r;r.moved(T1,r.cap(),v3(2.f,-2.25f,.125f));
  r.f.put(r.f.crate+k1().orientation+4,-1.f);   // M2 never writes orientation
  Capture out;COUNT(!r.op.restore(T1,Writer::Loaded,42,out,r.e));COUNT(is(r,Failure::Conflict));COUNT(r.f.sets.size()==1);}
 // The owner relocating onward from someone else's move is a conflict too:
 // otherwise a later restore would silently undo their move.
 {Rig r;r.moved(T1,r.cap(),v3(2.f,-2.25f,.125f));
  r.f.set_pos(r.f.crate,2.25f,-2.25f,.125f);Capture fresh=r.cap();
  // Not refused_write(): that helper asserts the ledger is unchanged, and
  // this refusal is the one that deliberately drops the entry.
  auto before=r.snap();Capture out;Status st=Status::Moved;
  COUNT(!r.move(T1,fresh,v3(2.5f,-2.25f,.125f),out,st));
  COUNT(is(r,Failure::Conflict,"moved by another writer; ownership released"));
  COUNT(r.snap().sets==before.sets);COUNT(untouched(out));COUNT(st==Status::Moved);
  COUNT(r.op.entry(42)==nullptr);COUNT(r.op.ledger_size()==0);
  COUNT(bit_equal(r.f.pos(r.f.crate),v3(2.25f,-2.25f,.125f)));
  // Released, so the same script may start over from the new pose.
  r.moved(T1,r.cap(),v3(2.5f,-2.25f,.125f));COUNT(r.op.owner_of(42)==T1);
  COUNT(bit_equal(r.op.entry(42)->origin_position,v3(2.25f,-2.25f,.125f)));}
}

// F2: restore's fence 6 (`bit_equal(cur.position, e.last_written)`) must
// catch a sign-only flip on a zero component the same way it catches any
// other move by another writer. Kills the `fence6` mutant (bit_equal ->
// engine_equal at that site).
void restore_conflict_on_signed_zero(){
 Rig r;Capture c=r.cap();
 Capture m=r.moved(T1,c,v3(2.f,-2.25f,0.f));
 r.f.set_pos(r.f.crate,2.f,-2.25f,-0.f);   // another writer, sign-only
 COUNT(engine_equal(m.position,r.f.pos(r.f.crate)));
 COUNT(!bit_equal(m.position,r.f.pos(r.f.crate)));
 auto before=r.snap();Capture out;
 COUNT(!r.op.restore(T1,Writer::Loaded,42,out,r.e));
 COUNT(is(r,Failure::Conflict,"moved by another writer; ownership released"));
 COUNT(r.snap().sets==before.sets);COUNT(r.op.entry(42)==nullptr);
}

// F2 (round 2): the same unreachability argument at fence 6. A NaN current
// position makes locate()/read_fields() refuse with Value before line 302's
// bit_equal/engine_equal choice is evaluated; restore's own handling of a
// non-Guard/Chain locate failure releases ownership (motion.cpp:288-292).
void restore_refused_on_nan_before_fence(){
 Rig r;r.moved(T1,r.cap(),v3(2.f,-2.25f,.125f));
 r.f.set_pos(r.f.crate,qnan,-2.25f,.125f);   // corrupted after the move
 Capture out;
 COUNT(!r.op.restore(T1,Writer::Loaded,42,out,r.e));
 COUNT(is(r,Failure::Value,"ownership released"));
 COUNT(r.op.entry(42)==nullptr);
}

// F2 (round 2): relocate's own ownership-consistency check (R10's
// `!bit_equal(cur.position, mine->last_written)`, motion.cpp:242) has the
// same bit_equal/engine_equal shape as the three named fences, but was not
// named by the review's F2 -- flagged there rather than fixed, since fixing
// it needs only a test (this one), no production line. Kills the
// `conflict` mutant (bit_equal -> engine_equal at that site), which was
// unkilled both before and after the rest of round 2
// (review-probes-motion-m2/mut/conflict/out.txt: 51/51, pre-existing).
void relocate_conflict_on_signed_zero(){
 Rig r;Capture c=r.cap();
 r.moved(T1,c,v3(2.f,-2.25f,0.f));
 r.f.set_pos(r.f.crate,2.f,-2.25f,-0.f);   // another writer, sign-only, after our move landed
 Capture fresh=r.cap();
 COUNT(engine_equal(r.op.entry(42)->last_written,fresh.position));
 COUNT(!bit_equal(r.op.entry(42)->last_written,fresh.position));
 auto before=r.snap();Capture out;Status st=Status::Moved;
 COUNT(!r.move(T1,fresh,v3(2.5f,-2.25f,0.f),out,st));
 COUNT(is(r,Failure::Conflict,"moved by another writer; ownership released"));
 COUNT(r.snap().sets==before.sets);COUNT(r.op.entry(42)==nullptr);
}

void second_owner_refused(){
 Rig r;Capture m=r.moved(T1,r.cap(),v3(2.f,-2.25f,.125f));
 refused_write(r,T2,m,v3(2.5f,-2.25f,.125f),Failure::Owned,"another script");
 Capture out;auto before=r.snap();
 COUNT(!r.op.restore(T2,Writer::Loaded,42,out,r.e));COUNT(is(r,Failure::NotOwner));
 COUNT(r.snap().calls==before.calls);   // not_owner is decided from the ledger alone
 COUNT(r.op.owner_of(42)==T1);
 // A different object is free for T2.
 r.f.placeable(0x1008000,43);r.f.put<std::int32_t>(0x1008000+k1().aabb_marker,-1);
 r.moved(T2,r.cap(43),v3(2.f,-2.25f,.125f));COUNT(r.op.owner_of(43)==T2&&r.op.owner_of(42)==T1);
}

void write_refused_without_host_owner_core(){
 Rig r;Capture c=r.cap();auto before=r.snap();
 refused_write(r,T1,c,v3(2.f,-2.25f,.125f),Failure::Unsupported,"only a loaded script",false,Writer::None);
 refused_write(r,0,c,v3(2.f,-2.25f,.125f),Failure::Unsupported,"only a loaded script");   // no token
 refused_write(r,T1,c,v3(2.f,-2.25f,.125f),Failure::Unsupported,"only a loaded script",false,Writer::Staged);
 COUNT(r.snap().reads==before.reads&&r.snap().calls==before.calls);
}

void unbind_clears_ledger(){
 Rig r;r.moved(T1,r.cap(),v3(2.f,-2.25f,.125f));COUNT(r.op.ledger_size()==1);
 r.op.unbind();COUNT(r.op.ledger_size()==0);
 CHECK(r.op.bind(k1().sha256,r.f.base,&r.f,r.e));COUNT(r.op.owner_of(42)==0);
}

std::uint64_t fake_tick=0;
std::uint64_t tick_source(void*){return fake_tick;}
void observe_reports_push_consumed_without_client_read(){
 Rig r;Capture c=r.cap();Observation o;
 COUNT(r.op.observe(42,c.object,o,r.e));COUNT(o.pushed&&!o.dirty_position&&!o.has_write&&!o.has_tick);
 bind_tick(tick_source,nullptr);fake_tick=100;
 Capture m=r.moved(T1,c,v3(2.f,-2.25f,.125f));
 fake_tick=100;COUNT(r.op.observe(42,m.object,o,r.e));
 COUNT(o.dirty_position&&!o.pushed&&o.push_gate_raw==1&&o.has_write&&o.has_tick&&o.ticks_since_write==0);
 // The per-tick consumer 0x4B0B70 clears bit value 2 only when +0x1F8 != 0.
 fake_tick=101;r.f.put<std::uint32_t>(r.f.crate+k1().dirty,0);
 COUNT(r.op.observe(42,m.object,o,r.e));COUNT(o.pushed&&o.ticks_since_write==1);
 r.f.put<std::uint32_t>(r.f.crate+k1().push_gate,0);
 COUNT(r.op.observe(42,m.object,o,r.e));COUNT(!o.pushed&&o.push_gate_raw==0);
 // Identity fence: a different object behind the id.
 COUNT(!r.op.observe(42,m.object+0x10,o,r.e));COUNT(is(r,Failure::Identity));
 // No setter call from observe, one getter per call.
 auto before=r.snap();COUNT(r.op.observe(42,m.object,o,r.e));
 COUNT(r.snap().sets==before.sets&&r.snap().calls==before.calls+1);
 bind_tick(nullptr,nullptr);COUNT(r.op.observe(42,m.object,o,r.e));COUNT(!o.has_tick);
}

void new_spans_match_reference_image(){
 // The M2 spans exist in the profile (deleting one fails here), and
 // spans_match_reference_image re-reads every span from the raw image.
 const Profile& p=k1();
 for(Address va:{Address(0x4cd1a0),Address(0x4cd1b1),Address(0x4cd1bd),Address(0x4cd1c8),Address(0x4cd202),
                 Address(0x4cd212),Address(0x4cd238)})
  COUNT(span_hex(va)!=nullptr);
 COUNT(p.set_position==0x4cd1a0);
 COUNT(std::string(span_hex(0x4cd1b1))=="e8cad7fdff");                // rel32 -> 0x4aa980
 std::uint32_t rel=0xfffdd7ca;COUNT(Address(0x4cd1b6+rel)%0x100000000ull==0x4aa980);
 COUNT(std::string(span_hex(0x4cd238)).substr(8)=="c21000");         // ret 0x10
 const char* env=std::getenv("KP_K1_GOG_IMAGE");const char* home=std::getenv("HOME");
 std::string path=env?env:(home?std::string(home):"")+"/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image";
 std::ifstream in(path,std::ios::binary);
 if(!in){std::cout<<"  SKIP reference image absent: "<<path<<"\n";return;}
 std::string image((std::istreambuf_iterator<char>(in)),std::istreambuf_iterator<char>());
 auto digit=[](char c){return c<='9'?c-'0':c-'a'+10;};
 for(Address va:{Address(0x4cd1b1),Address(0x4cd1bd),Address(0x4cd202),Address(0x4cd212),Address(0x4cd238)}){
  const char* hex=span_hex(va);
  for(std::size_t j=0;j*2<std::strlen(hex);++j)
   COUNT(static_cast<unsigned char>(image.at(va-p.preferred_base+j))==((digit(hex[j*2])<<4)|digit(hex[j*2+1])));
 }
}

// --- M2 Lua surface ------------------------------------------------------------
Writer lua_writer=Writer::Loaded;
Writer writer_probe(lua_State*,void*){return lua_writer;}
lua_State* motion_state(MotionFake& f){
 lua_State* L=luaL_newstate();luaL_openlibs(L);register_all(L);
 lua_pushlightuserdata(L,&f);
 lua_pushcclosure(L,[](lua_State* S)->int{
  lua_pushnumber(S,static_cast<MotionFake*>(lua_touserdata(S,lua_upvalueindex(1)))->calls);return 1;},1);
 lua_setglobal(L,"getter_calls");
 lua_pushlightuserdata(L,&f);
 lua_pushcclosure(L,[](lua_State* S)->int{
  lua_pushnumber(S,static_cast<MotionFake*>(lua_touserdata(S,lua_upvalueindex(1)))->sets.size());return 1;},1);
 lua_setglobal(L,"setter_calls");
 lua_pushlightuserdata(L,&f);
 lua_pushcclosure(L,[](lua_State* S)->int{
  lua_pushnumber(S,static_cast<MotionFake*>(lua_touserdata(S,lua_upvalueindex(1)))->reads);return 1;},1);
 lua_setglobal(L,"reads");
 lua_pushcfunction(L,[](lua_State* S)->int{gate_open=lua_toboolean(S,1)!=0;return 0;});lua_setglobal(L,"set_gate");
 lua_pushcfunction(L,[](lua_State* S)->int{
  const char* w=luaL_checkstring(S,1);
  lua_writer=!std::strcmp(w,"loaded")?Writer::Loaded:!std::strcmp(w,"staged")?Writer::Staged:Writer::None;return 0;});
 lua_setglobal(L,"set_writer");
 return L;
}
void run_in(lua_State* L,const char* program){
 if(luaL_dostring(L,program)){std::string err=lua_tostring(L,-1);throw std::runtime_error("lua: "+err);}
 ++checks;
}
struct LuaRig{
 MotionFake f;lua_State* L=nullptr;
 LuaRig():f(k1()){std::string e;CHECK(operations().bind(k1().sha256,f.base,&f,e));
  f.put<std::int32_t>(f.crate+k1().aabb_marker,-1);lua_writer=Writer::Loaded;bind_owner_probe(writer_probe,nullptr);L=motion_state(f);}
 ~LuaRig(){if(L)lua_close(L);bind_owner_probe(nullptr,nullptr);lua_writer=Writer::Loaded;operations().unbind();}
};

void lua_gate_refusal_before_args(){
 LuaRig r;
 run_in(r.L,R"(
  local c=assert(kp.motion.capture(42))
  local m=assert(kp.motion.relocate(c,{x=2,y=-2.25,z=0.125}))
  set_gate(false)
  local r0,s0,n0=reads(),setter_calls(),getter_calls()
  local want="unsupported: not on the engine thread"
  local function refused(...) local a,b=... assert(a==nil and b==want,tostring(b)) end
  refused(kp.motion.capture(42))
  refused(kp.motion.capture("not a number"))            -- gate before the argument check
  refused(kp.motion.relocate(m,{x=3,y=-2.25,z=0.125}))
  refused(kp.motion.relocate(nil,"junk"))              -- gate before argerror
  refused(kp.motion.restore(m))
  refused(kp.motion.observe(m))
  assert(reads()==r0 and setter_calls()==s0 and getter_calls()==n0)
  set_gate(true)
  assert(kp.motion.restore(m))
 )");
}

void write_refused_without_host_owner(){
 LuaRig r;
 bind_owner_probe(nullptr,nullptr);   // unbound probe: nobody may write
 run_in(r.L,R"(
  local c=assert(kp.motion.capture(42))
  local r0,n0=reads(),getter_calls()
  local m,err=kp.motion.relocate(c,{x=2,y=-2.25,z=0.125})
  assert(m==nil and err=="unsupported: only a loaded script can move placeables",err)
  assert(reads()==r0 and getter_calls()==n0 and setter_calls()==0)
 )");
 bind_owner_probe(writer_probe,nullptr);
 run_in(r.L,R"(
  set_writer("none")   -- console, harness or a bare state
  local c=assert(kp.motion.capture(42))                  -- reads stay allowed
  local m,err=kp.motion.relocate(c,{x=2,y=-2.25,z=0.125})
  assert(m==nil and err:find("^unsupported: only a loaded script"))
  local _,e2=kp.motion.restore(42) assert(e2:find("^unsupported: only a loaded script"))
  assert(setter_calls()==0)
 )");
}

void write_refused_while_staged(){
 LuaRig r;
 run_in(r.L,R"(
  set_writer("staged")   -- chunk top level, or the old generation during a reload
  local c=assert(kp.motion.capture(42))
  local m,err=kp.motion.relocate(c,{x=2,y=-2.25,z=0.125})
  assert(m==nil and err=="unsupported: only a loaded script can move placeables",err)
  assert(setter_calls()==0)
 )");
}

void restore_allowed_while_staged(){
 LuaRig r;
 run_in(r.L,R"(
  local c=assert(kp.motion.capture(42))
  local m,status=kp.motion.relocate(c,{x=2,y=-2.25,z=0.125})
  assert(status=="moved" and m.owned==true and m.position.x==2)
  set_writer("staged")
  local back=assert(kp.motion.restore(m))
  assert(back.position.x==1.5 and back.owned==false and setter_calls()==2)
  assert(kp.motion.capture(42).owned==false)
 )");
}

void owner_token_not_pointer(){
 LuaRig r;
 std::uint64_t a=state_token(r.L);COUNT(a!=0);
 run_in(r.L,R"(assert(kp.motion.relocate(kp.motion.capture(42),{x=2,y=-2.25,z=0.125})))");
 COUNT(operations().owner_of(42)==a);
 lua_close(r.L);r.L=nullptr;
 // A new state, whatever address the allocator hands out, gets a new token.
 r.L=motion_state(r.f);std::uint64_t b=state_token(r.L);
 COUNT(b!=0&&b!=a);
 // register_all twice on one state keeps its token.
 register_all(r.L);COUNT(state_token(r.L)==b);
 run_in(r.L,R"(
  local c=assert(kp.motion.capture(42))
  assert(c.owned==false)
  local _,e=kp.motion.restore(42) assert(e:find("^not_owner"),e)
  local _,e2=kp.motion.relocate(c,{x=2.5,y=-2.25,z=0.125}) assert(e2:find("^owned"),e2)
 )");
 COUNT(operations().owner_of(42)==a);   // still the closed state's orphan (M3 not landed)
 // A bare state that never ran register_all has token 0 and cannot write.
 lua_State* bare=luaL_newstate();COUNT(state_token(bare)==0);lua_close(bare);
}

void lua_relocate_surface(){
 LuaRig r;
 run_in(r.L,R"(
  local c=assert(kp.motion.capture(42))
  local function value(a,b) assert(a==nil and b:find("^value"),tostring(b)) end
  value(kp.motion.relocate(c,{x="2",y=-2.25,z=0.125}))       -- strings are not numbers
  value(kp.motion.relocate(c,{x=2,y=-2.25}))                 -- missing z
  value(kp.motion.relocate(c,{x=0/0,y=-2.25,z=0.125}))
  value(kp.motion.relocate(c,{x=1e39,y=-2.25,z=0.125}))      -- overflows a float
  value(kp.motion.relocate(c,42))
  value(kp.motion.relocate(c,{x=2,y=-2.25,z=0.125},{allow_stale_colision=true}))   -- typo refused
  value(kp.motion.relocate(c,{x=2,y=-2.25,z=0.125},{allow_stale_collision="yes"}))
  value(kp.motion.relocate(c,{x=2,y=-2.25,z=0.125},true))
  assert(not pcall(kp.motion.relocate,{},{x=2,y=-2.25,z=0.125}))   -- not a capture: argerror
  assert(setter_calls()==0)
  local m,s=kp.motion.relocate(c,{x=2,y=-2.25,z=0.125},{allow_stale_collision=false})
  assert(s=="moved" and m.position.x==2 and m.dirty_position==true)
  local n,s2=kp.motion.relocate(m,{x=2,y=-2.25,z=0.125})
  assert(s2=="noop" and n.owned==true and setter_calls()==1)
  local _,e=kp.motion.relocate(c,{x=3,y=-2.25,z=0.125}) assert(e:find("^stale"),e)   -- old capture
  local o=assert(kp.motion.observe(m))
  assert(o.pushed==false and o.dirty_position==true and o.client=="unverified" and o.ticks_since_write==nil)
  local back=assert(kp.motion.restore(42))                  -- by id
  assert(back.position.x==1.5)
  local _,e3=kp.motion.restore(1.5) assert(e3:find("^value"))
 )");
 // Walkmesh placeable: refused by default, opt-in allowed.
 r.f.put<std::int32_t>(r.f.crate+k1().aabb_marker,5);
 run_in(r.L,R"(
  local c=assert(kp.motion.capture(42)) assert(c.collision_registered)
  local m,e=kp.motion.relocate(c,{x=2,y=-2.25,z=0.125})
  assert(m==nil and e=="collision: placeable has a registered walkmesh; a raw move leaves it behind",e)
  assert(kp.motion.relocate(c,{x=2,y=-2.25,z=0.125},{allow_stale_collision=true}))
 )");
}

void capabilities_tables(){
 LuaRig r;
 run_in(r.L,R"(
  local caps=kp.motion.capabilities()
  assert(type(caps.reads)=="table" and type(caps.writes)=="table" and type(caps.refusals)=="table")
  local reads=table.concat(caps.reads,",")
  assert(reads=="id,area_id,position,orientation,facing,push_gate_raw,dirty_position,dirty_orientation,collision_registered,quaternion_raw,owned",reads)
  assert(#caps.writes==1 and caps.writes[1]=="position")
  local ref=table.concat(caps.refusals,",")
  assert(ref=="unsupported,guard,chain,identity,value,stale,collision,bounds,owned,not_owner,conflict,mutation",ref)
  -- The orchestrator ruling: allow_stale_collision is an explicit opt-in, default refuse.
  assert(caps.limits:find("allow_stale_collision",1,true) and caps.limits:find("refused by default",1,true))
  assert(caps.limits:find("save",1,true) and caps.limits:find("No auto-restore",1,true))
  -- Every read field named in caps.reads is served by a capture.
  local c=assert(kp.motion.capture(42))
  for _,k in ipairs(caps.reads) do assert(c[k]~=nil,k) end
 )");
}

// Names vs NWScript routines: case-insensitive, over every data/routines/*.json.
std::set<std::string> routine_names(const std::string& json,unsigned& count){
 std::set<std::string> out;count=0;const std::string key="\"name\": \"";
 for(std::size_t at=json.find(key);at!=std::string::npos;at=json.find(key,at+1)){
  std::size_t b=at+key.size(),e=json.find('"',b);std::string n=json.substr(b,e-b);
  std::transform(n.begin(),n.end(),n.begin(),[](unsigned char ch){return char(std::tolower(ch));});
  out.insert(n);++count;
 }
 return out;
}
void names_disjoint_from_nwscript_routines(){
 LuaRig r;
 std::vector<std::string> ours{"motion"};
 lua_getglobal(r.L,"kp");lua_getfield(r.L,-1,"motion");lua_pushnil(r.L);
 while(lua_next(r.L,-2)){ours.push_back(lua_tostring(r.L,-2));lua_pop(r.L,1);}
 lua_pop(r.L,2);
 COUNT(ours.size()==6);
 unsigned files=0;
 for(const auto& entry:std::filesystem::directory_iterator(source_root+"/data/routines")){
  if(entry.path().extension()!=".json")continue;
  unsigned count=0;auto names=routine_names(slurp(entry.path().string()),count);++files;
  std::string stem=entry.path().stem().string();
  if(stem=="k1")COUNT(count>=1848);
  if(stem=="k2")COUNT(count>=2082);
  COUNT(names.count("getposition")&&names.count("setfacing"));   // the scan sees routine names
  for(std::string n:ours){
   std::transform(n.begin(),n.end(),n.begin(),[](unsigned char ch){return char(std::tolower(ch));});
   if(names.count(n))throw std::runtime_error("kp.motion name "+n+" is an NWScript name in "+stem);
   ++checks;
  }
 }
 COUNT(files>=2);
}

} // namespace

int main(int argc,char** argv) {
 if(argc>1)source_root=argv[1];
 open_gate();
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
  // M2 (motion-m2-plan.md section 5)
  {"motion.gate_refusal_zero_reads_zero_calls",gate_refusal_zero_reads_zero_calls},
  {"motion.lua_gate_refusal_before_args",lua_gate_refusal_before_args},
  {"motion.nonfinite_refused_zero_calls",nonfinite_refused_zero_calls},
  {"motion.step_bound_refused",step_bound_refused},
  {"motion.dz_bound_refused",dz_bound_refused},
  {"motion.origin_range_refused",origin_range_refused},
  {"motion.stale_capture_pose_refused",stale_capture_pose_refused},
  {"motion.stale_capture_pose_refused_on_signed_zero",stale_capture_pose_refused_on_signed_zero},
  {"motion.stale_capture_refused_on_nan_before_fence",stale_capture_refused_on_nan_before_fence},
  {"motion.stale_epoch_refused",stale_epoch_refused},
  {"motion.area_change_refused",area_change_refused},
  {"motion.area_sentinel_refused",area_sentinel_refused},
  {"motion.collision_registered_refused_by_default",collision_registered_refused_by_default},
  {"motion.collision_opt_in_allows",collision_opt_in_allows},
  {"motion.relocate_single_setter_call_flags_110",relocate_single_setter_call_flags_110},
  {"motion.readback_requires_exact_pos_and_dirty_bit",readback_requires_exact_pos_and_dirty_bit},
  {"motion.readback_mismatch_reports_mutation_and_keeps_entry",readback_mismatch_reports_mutation_and_keeps_entry},
  {"motion.readback_mismatch_on_signed_zero",readback_mismatch_on_signed_zero},
  {"motion.readback_refused_on_nan_landed",readback_refused_on_nan_landed},
  {"motion.same_position_reported_noop_zero_setter_calls",same_position_reported_noop_zero_setter_calls},
  {"motion.restore_exact_readback",restore_exact_readback},
  {"motion.restore_refused_after_identity_change",restore_refused_after_identity_change},
  {"motion.restore_conflict_when_moved_by_other_writer_no_write",restore_conflict_when_moved_by_other_writer_no_write},
  {"motion.restore_conflict_on_signed_zero",restore_conflict_on_signed_zero},
  {"motion.restore_refused_on_nan_before_fence",restore_refused_on_nan_before_fence},
  {"motion.relocate_conflict_on_signed_zero",relocate_conflict_on_signed_zero},
  {"motion.second_owner_refused",second_owner_refused},
  {"motion.owner_token_not_pointer",owner_token_not_pointer},
  {"motion.write_refused_without_host_owner_core",write_refused_without_host_owner_core},
  {"motion.write_refused_without_host_owner",write_refused_without_host_owner},
  {"motion.write_refused_while_staged",write_refused_while_staged},
  {"motion.restore_allowed_while_staged",restore_allowed_while_staged},
  {"motion.unbind_clears_ledger",unbind_clears_ledger},
  {"motion.observe_reports_push_consumed_without_client_read",observe_reports_push_consumed_without_client_read},
  {"motion.lua_relocate_surface",lua_relocate_surface},
  {"motion.capabilities_tables",capabilities_tables},
  {"motion.new_spans_match_reference_image",new_spans_match_reference_image},
  {"motion.names_disjoint_from_nwscript_routines",names_disjoint_from_nwscript_routines},
 };
 unsigned failed=0;
 for(const auto& t:tests) {
  try{t.fn();std::cout<<"PASS "<<t.name<<"\n";}
  catch(const std::exception& e){++failed;std::cout<<"FAIL "<<t.name<<": "<<e.what()<<"\n";}
  operations().unbind();open_gate();bind_owner_probe(nullptr,nullptr);bind_tick(nullptr,nullptr);
 }
 std::cout<<(sizeof(tests)/sizeof(tests[0])-failed)<<"/"<<sizeof(tests)/sizeof(tests[0])<<" tests passed, "
          <<checks<<" checks (synthetic memory; no live ABI proof)\n";
 return failed?1:0;
}
