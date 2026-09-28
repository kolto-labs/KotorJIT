// Reviewer probe: adversarial cases against kp::api::motion::Operations (synthetic memory).
#include "api/motion.hpp"
#include <cstdio>
#include <cstring>
#include <cmath>
#include <map>
using namespace kp::api::motion;
struct Fake:Backend{
 const Profile& p; std::map<Address,unsigned char> b; unsigned calls=0;
 Address manager=0x1000000,server=0x1001000,internal=0x1002000,array=0x1003000,crate=0x1004000;
 template<class T>void put(Address a,T v){auto*c=reinterpret_cast<const unsigned char*>(&v);for(unsigned i=0;i<sizeof v;++i)b[a+i]=c[i];}
 void ptr(Address a,Address v){put(a,(std::uint32_t)v);}
 Fake(const Profile& pr):p(pr){
  for(auto&s:p.spans)if(s.va){auto d=[](char c){return c<='9'?c-'0':c-'a'+10;};for(size_t j=0;j*2<strlen(s.hex);++j)b[s.va+j]=(d(s.hex[j*2])<<4)|d(s.hex[j*2+1]);}
  for(auto&s:p.slots)if(s.va)ptr(s.va,s.target);
  ptr(p.manager_slot,manager);ptr(manager+p.manager_server,server);ptr(server+p.server_internal,internal);ptr(internal+p.internal_array,array);
  put<std::uint8_t>(array,1); // only the 1 byte the core probes; [array] as a dword (the hash table ptr) is NOT mapped
  ptr(crate,p.placeable_vtable);put(crate+p.id,(std::uint32_t)42);put<std::uint8_t>(crate+p.type,9);
  put<std::uint32_t>(crate+p.area_id,1);for(int i=0;i<3;++i)put(crate+p.position+4*i,0.f);
  put(crate+p.orientation,1.f);put(crate+p.orientation+4,-0.f);put(crate+p.orientation+8,0.f);
  put<std::uint32_t>(crate+p.push_gate,1);put<std::uint32_t>(crate+p.dirty,0);put<std::int32_t>(crate+p.aabb_marker,-1);
  for(int i=0;i<4;++i)put(crate+p.quaternion+4*i,0.f);
 }
 Abi abi()const override{return p.abi;} unsigned width()const override{return 4;}
 bool read(Address a,void*o,size_t n)const override{auto*c=(unsigned char*)o;for(size_t i=0;i<n;++i){auto it=b.find(a+i);if(it==b.end())return false;c[i]=it->second;}return true;}
 Address placeable(Address,Address,std::uint32_t id)override{++calls;return id==42?crate:0;}
};
int main(){
 const Profile& p=profiles().front(); Fake f(p); Operations op; std::string e;
 if(!op.bind(p.sha256,p.preferred_base,&f,e)){printf("bind failed %s\n",e.c_str());return 1;}
 Capture c; bool ok=op.capture(42,c,e);
 printf("P1 facing for orientation (1,-0,0): ok=%d facing=%g signbit=%d\n",ok,c.facing,(int)std::signbit(c.facing));
 printf("P2 getter reached with [array] dword unmapped (engine would deref it as the id hash table): calls=%u\n",f.calls);
 f.put(f.crate+p.orientation,0.f);f.put(f.crate+p.orientation+4,0.f);
 ok=op.capture(42,c,e);printf("P3 zero-length orientation: ok=%d facing=%g\n",ok,c.facing);
 // P4: which getter bytes are pinned by spans? ABI-defining bytes: 0x4b18d1 arg read, 0x4b190f/0x4b1915 ret 4
 for(Address va:{0x4b18d0ULL,0x4b18d1ULL,0x4b18e9ULL,0x4b18eeULL,0x4b190fULL,0x4b1915ULL}){
  bool cov=false;for(auto&s:p.spans)if(s.va&&va>=s.va&&va<s.va+strlen(s.hex)/2)cov=true;
  printf("P4 va 0x%llx guarded=%d\n",(unsigned long long)va,cov);}
 // P5: capture struct partial-write check with a sentinel-filled out on failure
 Capture s; s.id=0xdeadbeef; s.position={9,9,9}; f.put<std::uint8_t>(f.crate+p.type,5);
 ok=op.capture(42,s,e); printf("P5 failure keeps sentinel: ok=%d id=%x pos0=%g err='%s'\n",ok,s.id,s.position[0],e.c_str());
 return 0;
}
