#include "api/animation.hpp"
#include <array>
#include <cmath>
#include <cstring>
#include <iostream>
#include <limits>
#include <map>
#include <stdexcept>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
#include "lualib.h"
}
#define CHECK(x) do{if(!(x))throw std::runtime_error(std::string("line ")+std::to_string(__LINE__)+": "+#x);}while(0)
#include "tests/model_backend_fixture.hpp"
namespace A=kp::api::animation;
// model::Operations::bind takes the VA resolved for each of the profile's five
// sites (normally from a hookpack-admitted generated operation). As in
// kp_modeltest, these controlled-backend checks hand back the Profile's own
// compile-time sites.
static std::array<Address,5> generated_from(const Profile& p){
 std::array<Address,5> gen{};for(unsigned i=0;i<gen.size();++i)gen[i]=p.sites[i].va;return gen;
}
struct Anim: A::Backend {
 Fake& model;const A::Profile& profile;
 struct Clip{bool active;float time,duration,rate;};
 std::map<std::string,Clip> clips{{"pause1",{true,0,8.333f,1}},{"dance",{false,-1,2.06667f,1}},{"zero",{false,-1,0,1}}};
 int plays=0,queries=0;bool reset=false,override_run=false;std::vector<std::string> logs;
 Anim(Fake& m,const A::Profile& p):model(m),profile(p){
  for(const auto* site:{&p.play,&p.query}){
   auto digit=[](char c){return c<='9'?c-'0':c-'a'+10;};
   for(unsigned i=0;i<32;++i)model.bytes[address(*site)+i]=(digit(site->bytes[2*i])<<4)|digit(site->bytes[2*i+1]);
   if(site->rebased_u32>=0){auto a=address(*site)+site->rebased_u32;model.put(a,model.get<std::uint32_t>(a)+static_cast<std::uint32_t>(model.base-model.p.preferred_base));}
  }
 }
 Address address(const A::Site& s)const{return model.base+s.va-model.p.preferred_base;}
 Abi abi()const override{return model.abi();}unsigned width()const override{return model.width();}
 bool read(Address a,void* out,std::size_t n)const override{return model.read(a,out,n);}
 bool query(Address f,Address object,const char* name,float& time,float& duration)override{
  CHECK(f==address(profile.query)&&object==model.gob);++queries;
  auto it=clips.find(name);if(it==clips.end()){time=duration=-1;return false;}
  time=it->second.active?it->second.time:-1;duration=it->second.duration;return it->second.active;
 }
 bool play(Address f,Address object,const char* name,float rate,int flags,float start)override{
  CHECK(f==address(profile.play)&&object==model.gob&&flags==2);++plays;
  auto& clip=clips.at(name);if(!clip.active||reset)clip.time=start;clip.active=!override_run;clip.rate=rate;
  for(auto& [other,c]:clips)if(other!=name)c.active=false;
  if(reset)clip.time=0;
  return true;
 }
 void advance(float seconds){for(auto& [_,c]:clips)if(c.active)c.time+=seconds*c.rate;}
 void log(const std::string& text)override{logs.push_back(text);}
};
void test(unsigned index){
 Fake f(profiles()[index]);Anim backend(f,A::profiles()[index]);Operations models;std::string error;
 auto gen=generated_from(f.p);CHECK(models.bind(f.p.sha256,f.base,&f,&gen,error));Capture capture;CHECK(models.snapshot(42,capture,error));
 A::Operations op;A::State state;
 CHECK(!op.bind("wrong",f.base,&models,&backend,error));
 f.host_width=f.p.width==4?8:4;CHECK(!op.bind(f.p.sha256,f.base,&models,&backend,error));f.host_width=f.p.width;
 f.host_abi=f.p.abi==Abi::Win32?Abi::Darwin32:Abi::Win32;CHECK(!op.bind(f.p.sha256,f.base,&models,&backend,error));f.host_abi=f.p.abi;
 auto at=backend.address(backend.profile.play);auto byte=f.bytes[at];f.bytes[at]^=1;
 CHECK(!op.bind(f.p.sha256,f.base,&models,&backend,error));f.bytes[at]=byte;
 CHECK(op.bind(f.p.sha256,f.base,&models,&backend,error));
 auto query_at=backend.address(backend.profile.query);f.bytes[query_at]^=1;
 CHECK(!op.inspect(capture,"dance",state,error));f.bytes[query_at]^=1;
 if(backend.profile.play.rebased_u32>=0){
  auto operand=at+backend.profile.play.rebased_u32;f.bytes[operand]^=1;
  CHECK(!op.inspect(capture,"dance",state,error));f.bytes[operand]^=1;
 }
 CHECK(op.inspect(capture,"dance",state,error)&&state.available&&!state.active&&state.time==-1&&state.duration<3);
 CHECK(op.inspect(capture,"missing",state,error)&&!state.available&&!state.active);
 for(const std::string& name:{std::string(),std::string("NULL"),std::string("CuRrEnT"),std::string(32,'x'),std::string("dance\0x",7),std::string("bad-name")})CHECK(!op.inspect(capture,name,state,error));
 for(float n:{-1.f,2.1f,std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN()})CHECK(!op.cue(capture,"dance",n,{},state,error));
 CHECK(!op.cue(capture,"dance",1,-1,state,error));CHECK(!op.cue(capture,"dance",1,3,state,error));
 CHECK(!op.cue(capture,"dance",1,std::numeric_limits<float>::quiet_NaN(),state,error));
 CHECK(!op.cue(capture,"zero",1,{},state,error));CHECK(!op.cue(capture,"missing",1,{},state,error));CHECK(backend.plays==0);
 CHECK(op.cue(capture,"dance",.5f,0,state,error)&&state.active&&state.time==0);
 backend.advance(1);CHECK(op.inspect(capture,"dance",state,error)&&state.time==.5f);
 CHECK(!op.cue(capture,"dance",0,0,state,error)); // No seeking an active run.
 CHECK(op.cue(capture,"dance",0,{},state,error)&&state.time==.5f);
 backend.advance(2);CHECK(op.inspect(capture,"dance",state,error)&&state.time==.5f);
 CHECK(op.cue(capture,"dance",.5f,{},state,error));backend.advance(.5f);
 CHECK(op.inspect(capture,"dance",state,error)&&state.time==.75f&&backend.plays==3);
 backend.reset=true;CHECK(!op.cue(capture,"dance",0,{},state,error));backend.reset=false;
 backend.override_run=true;CHECK(!op.cue(capture,"dance",1,{},state,error));backend.override_run=false;
 backend.clips["dance"].duration=std::numeric_limits<float>::quiet_NaN();CHECK(!op.inspect(capture,"dance",state,error));backend.clips["dance"].duration=2.06667f;
 auto count=backend.plays;f.gob+=0x1000;f.setup_model(f.gob,1,1.5f);
 CHECK(!op.cue(capture,"dance",1,{},state,error)&&backend.plays==count);
 models.unbind();CHECK(!op.inspect(capture,"dance",state,error));
}
void lua_test(){
 Fake f(profiles().back());Anim backend(f,A::profiles().back());std::string error;
 auto gen=generated_from(f.p);CHECK(operations().bind(f.p.sha256,f.base,&f,&gen,error));CHECK(A::operations().bind(f.p.sha256,f.base,&operations(),&backend,error));
 lua_State* L=luaL_newstate();luaL_openlibs(L);register_all(L);A::register_all(L);
 const char* script=R"(
 local c=assert(kp.model.snapshot(42));assert(kp.animation.capabilities().available)
 assert(kp.animation.inspect(c,'dance').units=='seconds')
 assert(not kp.animation.inspect(c,'dance').active)
 assert(kp.animation.cue(c,'dance',0.5,0).active)
 assert(kp.animation.cue(c,'dance',0).time==0)
 assert(kp.animation.cue(c,'dance',0.5).active)
 assert(kp.animation.inspect(c,'x\0y')==nil)
 assert(kp.animation.cue(c,'dance',0/0)==nil)
 local fake=newproxy(true);debug.setmetatable(fake,debug.getmetatable(c))
 assert(not pcall(kp.animation.inspect,fake,'dance'))
 assert(kp.ActionPlayAnimation==nil and nwscript==nil)
 )";
 if(luaL_dostring(L,script)!=0)throw std::runtime_error(lua_tostring(L,-1));
 lua_close(L);A::operations().unbind();operations().unbind();
}
int main(){try{for(unsigned i=0;i<4;++i)test(i);lua_test();std::cout<<"animation core/Lua/profile clock checks passed; controlled backend only\n";return 0;}catch(const std::exception& e){std::cerr<<e.what()<<'\n';return 1;}}
