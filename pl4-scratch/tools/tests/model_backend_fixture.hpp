#pragma once
// Controlled object memory shared by native model/animation tests. Requires CHECK.
#include "api/model.hpp"
#include <map>
#include <vector>
#include <string>
#include <cstring>
using namespace kp::api::model;
using OriginalConvert=std::uint32_t(__attribute__((stdcall)) *)(std::uint32_t);
struct Fake:Backend {
 const Profile& p;std::map<Address,unsigned char> bytes;
 Address base,manager=0x1000000,client=0x1001000,internal=0x1002000,array=0x1003000,actor=0x1004000,anim=0x1005000,gob=0x1006000,vt=0x1007000;
 std::uint32_t server_id=42,client_id=73;OriginalConvert original_convert=nullptr;
 Address server=0x1010000,server_internal=0x1011000,server_array=0x1012000,server_actor=0x1013000;
 unsigned setters=0,conversions=0,lookups=0;std::vector<std::string> logs;
 bool mutate=true,accept=true,replace_after=false;unsigned host_width;Abi host_abi;
 explicit Fake(const Profile& profile):p(profile),base(p.preferred_base+0x10000),host_width(p.width),host_abi(p.abi){
  for(unsigned i=0;i<p.sites.size();++i)if(p.sites[i].va)for(unsigned j=0;j<16;++j) {
   auto digit=[](char c){return c<='9'?c-'0':c-'a'+10;};
   bytes[site(i)+j]=(digit(p.sites[i].bytes[j*2])<<4)|digit(p.sites[i].bytes[j*2+1]);
  }
  ptr(base+p.manager_slot-p.preferred_base,manager);ptr(manager+p.manager_client,client);
  ptr(client+p.client_internal,internal);ptr(internal+p.internal_array,array);put<std::uint8_t>(array,1);
  put<std::uint8_t>(actor+p.type_offset,5);ptr(actor+(p.width==8?0x80:0x68),anim);put<std::uint8_t>(anim,1);
  setup_model(gob,1,1.5f);
  if(p.sites[4].va) {
   ptr(manager+p.manager_server,server);ptr(server+p.width,server_internal);
   ptr(server_internal+p.server_array,server_array);put<std::uint8_t>(server_array,1);
   put(server_actor+p.width,server_id);put<std::uint8_t>(server_actor+p.type_offset,5);
  }
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
 std::uint32_t convert(Address f,Address c,std::uint32_t id)override{CHECK(f==site(0)&&c==client&&id==server_id);++conversions;return original_convert?original_convert(id):client_id;}
 Address creature(Address f,Address c,std::uint32_t id)override{CHECK(f==site(1)&&c==client&&id==client_id);CHECK(conversions>lookups);++lookups;return actor;}
 Address server_object(Address f,Address owner,std::uint32_t id)override{CHECK(f==site(4)&&owner==server&&id==server_id);return server_actor;}
 Address model(Address f,Address c)override{CHECK(f==site(2)&&c==actor);return gob;}
 bool set_scale(Address f,Address m,float scale)override{
  CHECK(f==site(3)&&m==gob);++setters;
  if(mutate){float ratio=get<float>(gob+p.effective_offset)/get<float>(gob+p.base_offset);put(gob+p.effective_offset,ratio*scale);put(gob+p.base_offset,scale);}
  if(replace_after){gob+=0x2000;setup_model(gob,1,1.5);}
  return accept;
 }
 void log(const std::string& message)override{logs.push_back(message);}
};
