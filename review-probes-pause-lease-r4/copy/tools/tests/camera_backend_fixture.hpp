#pragma once
// Sparse synthetic memory for kp.camera tests. Requires CHECK.
// Only mapped bytes are readable; every read is recorded so a test can prove
// that a non-chase behaviour's chase-relative offsets were never touched.
#include "api/camera.hpp"
#include <cstring>
#include <map>
#include <vector>
using namespace kp::api::camera;
struct CameraFake:Backend {
 const Profile& p;std::map<Address,unsigned char> bytes;
 mutable std::vector<std::pair<Address,std::size_t>> reads;
 Address base;
 Address manager=0x1000000,client=0x1001000,internal=0x1002000,module=0x1003000,options=0x1004000,
         camera=0x1005000,beh=0x1006000;
 unsigned host_width;Abi host_abi;
 explicit CameraFake(const Profile& profile):p(profile),base(p.preferred_base),host_width(p.width),host_abi(p.abi){
  for(const auto& s:p.spans)if(s.va){
   auto digit=[](char c){return c<='9'?c-'0':c-'a'+10;};
   for(std::size_t j=0;j*2<std::strlen(s.hex);++j)bytes[s.va+j]=(digit(s.hex[j*2])<<4)|digit(s.hex[j*2+1]);
  }
  for(const auto& s:p.slots)if(s.va)ptr(s.va,s.target);
  ptr(p.manager_slot,manager);ptr(manager+p.manager_client,client);ptr(client+p.client_internal,internal);
  ptr(internal+p.internal_module,module);ptr(internal+p.internal_options,options);
  put<std::uint8_t>(options+p.options_mode,2);put<std::int32_t>(p.pending_style,-1);
  ptr(module,p.module_vtable);ptr(module+p.module_camera,camera);
  ptr(camera,p.camera_vtable);ptr(camera+p.camera_behavior,beh);
  chase(beh);
 }
 void chase(Address b){
  ptr(b,p.chase_vtable);
  put(b+p.dist,6.25f);put(b+p.speed,20.f);put(b+p.pitch,80.f);put(b+p.height,3.5f);
  put<std::uint32_t>(b+p.dolly,0);put(b+p.base_distance,6.25f);put(b+p.base_view_angle,55.f);
  put<std::int32_t>(b+p.style_row,3);
  for(unsigned i=0;i<4;++i)put(b+p.raw_28+i*4,.1f*(i+1));
  for(unsigned i=0;i<3;++i){put(b+p.raw_38+i*4,10.f+i);put(b+p.raw_50+i*4,20.f+i);}
 }
 template<class T>void put(Address a,T value){const auto* b=reinterpret_cast<const unsigned char*>(&value);for(unsigned i=0;i<sizeof(value);++i)bytes[a+i]=b[i];}
 void ptr(Address a,Address value){put(a,static_cast<std::uint32_t>(value));}
 void unmap(Address a,std::size_t n){for(std::size_t i=0;i<n;++i)bytes.erase(a+i);}
 Abi abi()const override{return host_abi;}
 unsigned width()const override{return host_width;}
 bool read(Address a,void* out,std::size_t n)const override{
  reads.emplace_back(a,n);auto* b=static_cast<unsigned char*>(out);
  for(std::size_t i=0;i<n;++i){auto it=bytes.find(a+i);if(it==bytes.end())return false;b[i]=it->second;}
  return true;
 }
 bool touched(Address from,Address to)const{
  for(const auto& r:reads)if(r.first<to && r.first+r.second>from)return true;
  return false;
 }
};
