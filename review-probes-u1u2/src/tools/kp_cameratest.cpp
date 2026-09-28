// kp.camera Stage 1 offline tests: profile gating, exact guards, pointer
// chain, chase/other decoding, value checks and the protected Lua surface.
// Synthetic memory only; this proves nothing about the live game.
#include "api/camera.hpp"
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
#define CHECK(x) do{if(!(x))throw std::runtime_error(std::string("line ")+std::to_string(__LINE__)+": "+#x);}while(0)
#include "tests/camera_backend_fixture.hpp"

namespace {
const Profile& k1(){return profiles().front();}
unsigned checks=0;
#define COUNT(x) do{CHECK(x);++checks;}while(0)

void profile_gating() {
 COUNT(profiles().size()==1);COUNT(std::string(k1().name)=="windows-k1-gog");
 CameraFake f(k1());Operations op;std::string e;
 // Every other known build fails closed at bind.
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
 // Spans embed absolute immediates, so a relocated image is refused.
 COUNT(!op.bind(k1().sha256,f.base+0x10000,&f,e));COUNT(op.last_failure()==Failure::Unsupported);
 COUNT(e.find("relocated")!=std::string::npos);
 // Unbound snapshot is a typed unsupported failure.
 Capture c;COUNT(!op.snapshot(c,e));COUNT(op.last_failure()==Failure::Unsupported);
 // This Linux test host has no native adapter.
 COUNT(native_backend([](model::Address,void*,std::size_t,void*){return false;},nullptr)==nullptr);
 COUNT(!bind_native(k1().sha256,0x400000,[](model::Address,void*,std::size_t,void*){return false;},nullptr,e));
 COUNT(!operations().available());
 COUNT(op.bind(k1().sha256,f.base,&f,e));COUNT(op.available());COUNT(op.last_failure()==Failure::None);
}

void span_validation() {
 for(const auto& s:k1().spans)if(s.va)COUNT(Operations::valid_span(s));
 COUNT(!Operations::valid_span({0x1000,""}));
 COUNT(!Operations::valid_span({0x1000,"8b490"}));               // odd length
 COUNT(!Operations::valid_span({0x1000,"8B4904"}));              // uppercase is not the stored form
 COUNT(!Operations::valid_span({0x1000,"8g4904"}));              // non-hex
 COUNT(!Operations::valid_span({0x1000,"00112233445566778899aabbccddeeff00"})); // 17 bytes
 COUNT(Operations::valid_span({0x1000,"00112233445566778899aabbccddeeff"}));    // 16 bytes
 COUNT(!Operations::valid_span({0x1000,nullptr}));
}

void guard_flips() {
 unsigned spans=0,bytes=0;
 for(const auto& s:k1().spans) {
  if(!s.va)continue;++spans;
  for(std::size_t j=0;j*2<std::strlen(s.hex);++j) {
   ++bytes;
   CameraFake f(k1());Operations op;std::string e;
   f.bytes[s.va+j]^=0x01;
   COUNT(!op.bind(k1().sha256,f.base,&f,e));COUNT(op.last_failure()==Failure::Guard);
   f.bytes[s.va+j]^=0x01;
   COUNT(op.bind(k1().sha256,f.base,&f,e));
   f.bytes[s.va+j]^=0x80;                       // flipped after bind
   Capture c;COUNT(!op.snapshot(c,e));COUNT(op.last_failure()==Failure::Guard);
   COUNT(e.find("guard")!=std::string::npos);
   f.unmap(s.va+j,1);                           // unreadable guard byte
   COUNT(!op.snapshot(c,e));COUNT(op.last_failure()==Failure::Guard);
  }
 }
 COUNT(spans==31);COUNT(bytes>=150);
 for(const auto& s:k1().slots) {
  if(!s.va)continue;
  CameraFake f(k1());Operations op;std::string e;
  f.ptr(s.va,s.target+1);COUNT(!op.bind(k1().sha256,f.base,&f,e));COUNT(op.last_failure()==Failure::Guard);
  f.ptr(s.va,s.target);COUNT(op.bind(k1().sha256,f.base,&f,e));
  f.ptr(s.va,0);Capture c;COUNT(!op.snapshot(c,e));COUNT(op.last_failure()==Failure::Guard);
 }
}

void chase_snapshot() {
 CameraFake f(k1());Operations op;std::string e;Capture c;
 COUNT(op.bind(k1().sha256,f.base,&f,e));COUNT(op.snapshot(c,e));COUNT(op.last_failure()==Failure::None);
 COUNT(c.behavior==Behavior::Chase);COUNT(c.mode==2);COUNT(c.pending_style==-1);
 COUNT(c.distance==6.25f&&c.speed==20.f&&c.pitch==80.f&&c.height==3.5f);
 COUNT(c.dolly==0&&c.base_distance==6.25f&&c.base_view_angle==55.f&&c.style_row==3);
 COUNT(c.raw_28[0]==.1f&&c.raw_28[3]==.4f&&c.raw_38[0]==10.f&&c.raw_38[2]==12.f&&c.raw_50[1]==21.f);
 COUNT(c.module==f.module&&c.camera==f.camera&&c.behavior_ptr==f.beh&&c.behavior_vtable==k1().chase_vtable);
 COUNT(c.epoch==op.epoch());
 // Raw integers are preserved, including -1 and nonzero garbage.
 f.put<std::uint32_t>(f.beh+k1().dolly,0xdeadbeef);f.put<std::int32_t>(f.beh+k1().style_row,-1);
 f.put<std::int32_t>(k1().pending_style,7);f.put<std::uint8_t>(f.options+k1().options_mode,0xff);
 COUNT(op.snapshot(c,e));COUNT(c.dolly==0xdeadbeef&&c.style_row==-1&&c.pending_style==7&&c.mode==0xff);
 // Staleness: rebinding advances the epoch.
 auto first=c.epoch;op.unbind();COUNT(!op.snapshot(c,e));COUNT(op.last_failure()==Failure::Unsupported);
 COUNT(op.bind(k1().sha256,f.base,&f,e));COUNT(op.snapshot(c,e));COUNT(c.epoch!=first);
}

void other_behavior() {
 // Sparse memory: only the other behaviour's vtable word exists. Snapshot
 // succeeds and never reads a chase-relative offset.
 CameraFake f(k1());Operations op;std::string e;Capture c;
 f.unmap(f.beh,0x200);f.ptr(f.beh,0x751000);
 COUNT(op.bind(k1().sha256,f.base,&f,e));f.reads.clear();
 COUNT(op.snapshot(c,e));COUNT(c.behavior==Behavior::Other);COUNT(c.behavior_vtable==0x751000);
 COUNT(c.mode==2&&c.pending_style==-1&&c.behavior_ptr==f.beh);
 COUNT(!f.touched(f.beh+4,f.beh+0x200));COUNT(f.touched(f.beh,f.beh+4));
 COUNT(c.distance==0&&c.dolly==0&&c.style_row==-1);
 // Chase vtable written but another object layout: still only vtable identity decides.
 f.ptr(f.beh,0x743924);COUNT(op.snapshot(c,e));COUNT(c.behavior==Behavior::Other);
}

void chain_failures() {
 const Profile& p=k1();
 // Each hop: null pointer and unmapped pointer fail as Chain and name the hop.
 auto run=[&](const char* hop,auto mutate){
  CameraFake f(p);Operations op;std::string e;Capture c;COUNT(op.bind(p.sha256,f.base,&f,e));
  mutate(f);COUNT(!op.snapshot(c,e));COUNT(op.last_failure()==Failure::Chain);
  COUNT(e.find(hop)!=std::string::npos);
 };
 run("app manager",[&](CameraFake& f){f.ptr(p.manager_slot,0);});
 run("app manager",[&](CameraFake& f){f.unmap(p.manager_slot,4);});
 run("client",[&](CameraFake& f){f.ptr(f.manager+p.manager_client,0);});
 run("client",[&](CameraFake& f){f.unmap(f.manager+p.manager_client,4);});
 run("client internal",[&](CameraFake& f){f.ptr(f.client+p.client_internal,0);});
 run("client internal",[&](CameraFake& f){f.unmap(f.client+p.client_internal,4);});
 run("module",[&](CameraFake& f){f.ptr(f.internal+p.internal_module,0);});
 run("module",[&](CameraFake& f){f.unmap(f.internal+p.internal_module,4);});
 run("module",[&](CameraFake& f){f.unmap(f.module,4);});
 run("options",[&](CameraFake& f){f.ptr(f.internal+p.internal_options,0);});
 run("options",[&](CameraFake& f){f.unmap(f.options+p.options_mode,1);});
 run("camera",[&](CameraFake& f){f.ptr(f.module+p.module_camera,0);});
 run("camera",[&](CameraFake& f){f.unmap(f.module+p.module_camera,4);});
 run("camera",[&](CameraFake& f){f.unmap(f.camera,4);});
 run("behaviour",[&](CameraFake& f){f.ptr(f.camera+p.camera_behavior,0);});
 run("behaviour",[&](CameraFake& f){f.unmap(f.camera+p.camera_behavior,4);});
 run("behaviour",[&](CameraFake& f){f.unmap(f.beh,4);});
 run("pending style",[&](CameraFake& f){f.unmap(p.pending_style,4);});
 run("chase field",[&](CameraFake& f){f.unmap(f.beh+p.height,4);});
 run("chase field",[&](CameraFake& f){f.unmap(f.beh+p.raw_50+8,4);});
 run("chase field",[&](CameraFake& f){f.unmap(f.beh+p.style_row,4);});
 // Owner and camera identity are vtable guards: a mismatch is a typed guard failure
 // carrying the observed value, never an identity-only capture.
 {
  CameraFake f(p);Operations op;std::string e;Capture c;COUNT(op.bind(p.sha256,f.base,&f,e));
  f.ptr(f.module,0x751000);COUNT(!op.snapshot(c,e));COUNT(op.last_failure()==Failure::Guard);
  COUNT(e.find("0x751000")!=std::string::npos);
  f.ptr(f.module,p.module_vtable);f.ptr(f.camera,0x741000);COUNT(!op.snapshot(c,e));
  COUNT(op.last_failure()==Failure::Guard);COUNT(e.find("0x741000")!=std::string::npos);
 }
}

void value_failures() {
 const Profile& p=k1();
 for(unsigned off:{p.dist,p.speed,p.pitch,p.height,p.base_distance,p.base_view_angle,
                   p.raw_28,p.raw_28+12,p.raw_38,p.raw_38+8,p.raw_50,p.raw_50+8}) {
  for(float bad:{std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::infinity(),
                 -std::numeric_limits<float>::infinity()}) {
   CameraFake f(p);Operations op;std::string e;Capture c;COUNT(op.bind(p.sha256,f.base,&f,e));
   f.put(f.beh+off,bad);COUNT(!op.snapshot(c,e));COUNT(op.last_failure()==Failure::Value);
   COUNT(e.find("non-finite")!=std::string::npos);
  }
 }
}

int forged(lua_State* L) {
 auto size=lua_objlen(L,1);void* memory=lua_newuserdata(L,size);std::memset(memory,0,size);
 lua_getmetatable(L,1);lua_setmetatable(L,-2);return 1;
}
void run_lua(lua_State* L,const char* program) {
 if(luaL_dostring(L,program)!=0)throw std::runtime_error(lua_tostring(L,-1));
 ++checks;
}
void lua_tests() {
 CameraFake f(k1());std::string e;
 lua_State* L=luaL_newstate();luaL_openlibs(L);register_all(L);
 lua_pushcfunction(L,forged);lua_setglobal(L,"fake_capture");
 operations().unbind();
 run_lua(L,R"(
  local caps=kp.camera.capabilities()
  assert(caps.available==false and caps.profile=='unsupported' and caps.writes==false)
  local s,msg,code=kp.camera.snapshot()
  assert(s==nil and code=='unsupported' and msg:find('unsupported'),tostring(msg))
  for k,v in pairs(kp.camera) do assert(k==k:lower() and type(v)=='function','key '..k) end
  for _,k in ipairs({'set_distance','restore','write','SetCameraFacing','GetCameraFacing','SetCameraMode'}) do
   assert(kp.camera[k]==nil,k)
  end
 )");
 CHECK(operations().bind(k1().sha256,f.base,&f,e));
 run_lua(L,R"(
  local caps=kp.camera.capabilities()
  assert(caps.available==true and caps.profile=='windows-k1-gog' and caps.writes==false)
  assert(caps.abi=='windows-i386-thiscall' and caps.limits:find('no live proof'))
  local s=assert(kp.camera.snapshot())
  assert(s.behavior=='chase' and s.mode==2 and s.pending_style==-1)
  assert(s.distance==6.25 and s.speed==20 and s.pitch==80 and s.height==3.5)
  assert(s.dolly==0 and s.base_distance==6.25 and s.base_view_angle==55 and s.style_row==3)
  local q=s.raw_28_unverified assert(#q==4 and math.abs(q[1]-0.1)<1e-6)
  assert(#s.raw_38_unverified==3 and s.raw_38_unverified[1]==10 and s.raw_50_unverified[3]==22)
  assert(s.camera=='0x1005000' and s.behavior_ptr=='0x1006000' and s.module=='0x1003000')
  assert(s.behavior_vtable=='0x75165c')
  assert(s.nonexistent==nil)
  assert(not pcall(function() s.distance=9 end))
  assert(getmetatable(s)=='protected camera capture')
  assert(not pcall(setmetatable,s,{}))
  local forged=newproxy(true);debug.setmetatable(forged,debug.getmetatable(s))
  assert(not pcall(function() return forged.distance end))
  assert(not pcall(function() return fake_capture(s).distance end))
 )");
 f.bytes[k1().spans[5].va]^=1;
 run_lua(L,R"(local s,m,c=kp.camera.snapshot();assert(s==nil and c=='guard',tostring(m)))");
 f.bytes[k1().spans[5].va]^=1;
 f.ptr(f.camera+k1().camera_behavior,0);
 run_lua(L,R"(local s,m,c=kp.camera.snapshot();assert(s==nil and c=='chain' and m:find('behaviour'),tostring(m)))");
 f.ptr(f.camera+k1().camera_behavior,f.beh);
 f.put(f.beh+k1().dist,std::numeric_limits<float>::quiet_NaN());
 run_lua(L,R"(local s,m,c=kp.camera.snapshot();assert(s==nil and c=='value',tostring(m)))");
 f.unmap(f.beh,0x200);f.ptr(f.beh,0x751000);
 run_lua(L,R"(
  local s=assert(kp.camera.snapshot())
  assert(s.behavior=='other' and s.behavior_vtable=='0x751000')
  for _,k in ipairs({'distance','speed','pitch','height','dolly','base_distance','base_view_angle',
                     'style_row','raw_28_unverified','raw_38_unverified','raw_50_unverified'}) do
   assert(s[k]==nil,k)
  end
  assert(s.mode==2 and s.pending_style==-1)
 )");
 lua_close(L);operations().unbind();
}
} // namespace

int main(){
 try{
  profile_gating();span_validation();guard_flips();chase_snapshot();other_behavior();
  chain_failures();value_failures();lua_tests();
  std::cout<<"camera checks passed: "<<checks<<" (K1 GOG profile, synthetic memory; no live proof)\n";
  return 0;
 }catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}
}
