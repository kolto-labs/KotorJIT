#include "api/animation.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <sstream>
namespace kp::api::animation {
namespace {
bool fail(std::string& error,const char* why){error=why;return false;}
bool name_ok(const std::string& name){
 if(name.empty()||name.size()>31)return false;
 std::string lower;
 for(unsigned char c:name){
  if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_'))return false;
  lower+=c>='A'&&c<='Z'?static_cast<char>(c+32):static_cast<char>(c);
 }
 return lower!="null"&&lower!="current";
}
}
Operations& operations(){static Operations op;return op;}
void Operations::unbind(){profile_=nullptr;model_profile_=nullptr;models_=nullptr;backend_=nullptr;loaded_base_=0;}
Address Operations::address(const Site& s)const{return loaded_base_+s.va-model_profile_->preferred_base;}
bool Operations::guards(std::string& error)const {
 if(!backend_||!models_||!models_->available()||models_->profile()!=model_profile_||models_->image_base()!=loaded_base_)
  return fail(error,"unsupported: animation/model binding unavailable or changed");
 for(const Site* site:{&profile_->play,&profile_->query}){
  unsigned char expected[32]{},actual[32]{};
  if(std::strlen(site->bytes)!=64)return fail(error,"invalid animation code guard");
  auto digit=[](char c){return c<='9'?c-'0':c-'a'+10;};
  for(unsigned i=0;i<32;++i)expected[i]=(digit(site->bytes[2*i])<<4)|digit(site->bytes[2*i+1]);
  if(site->rebased_u32>=0){
   const auto offset=static_cast<unsigned>(site->rebased_u32);
   if(offset>28)return fail(error,"invalid animation relocation guard");
   std::uint32_t original=0;std::memcpy(&original,expected+offset,4);
   const std::int64_t relocated=static_cast<std::int64_t>(original)+static_cast<std::int64_t>(loaded_base_)-static_cast<std::int64_t>(model_profile_->preferred_base);
   if(relocated<0||relocated>0xffffffffLL)return fail(error,"invalid animation relocation slide");
   const auto value=static_cast<std::uint32_t>(relocated);std::memcpy(expected+offset,&value,4);
  }
  if(!backend_->read(address(*site),actual,32)||std::memcmp(expected,actual,32)!=0)
   return fail(error,"unsupported: animation function code guard mismatch");
 }
 return true;
}
bool Operations::bind(const std::string& sha,Address base,model::Operations* models,Backend* backend,std::string& error){
 unbind();error.clear();auto* p=model::profile_for(sha);
 if(!p||!models||!models->available()||models->profile()!=p||models->image_base()!=base)
  return fail(error,"unsupported: exact verified model/image binding required");
 if(!backend||backend->abi()!=p->abi||backend->width()!=p->width)
  return fail(error,"unsupported: animation OS/ABI/width mismatch");
 for(const auto& entry:profiles())if(std::string(entry.model_profile)==p->name)profile_=&entry;
 if(!profile_)return fail(error,"unsupported animation profile");
 const Address max=p->width==4?0xffffffffULL:std::numeric_limits<Address>::max();
 if(base>max-32||profile_->play.va-p->preferred_base>max-base-32||profile_->query.va-p->preferred_base>max-base-32){unbind();return fail(error,"invalid animation slide");}
 models_=models;model_profile_=p;loaded_base_=base;backend_=backend;
 if(!guards(error)){unbind();return false;}return true;
}
bool Operations::resolve(const model::Capture& capture,model::Capture& current,std::string& error)const {
 return guards(error)&&models_->refresh(capture,current,error);
}
bool Operations::read_state(Address model,const std::string& clip,State& out,std::string& error){
 out={};out.active=backend_->query(address(profile_->query),model,clip.c_str(),out.time,out.duration);
 if(!std::isfinite(out.duration)||!std::isfinite(out.time)||(out.duration<0&&out.duration!= -1) ||
    (out.active&&(out.duration<=0||out.time< -0.00001f||out.time>out.duration+0.001f))||
    (!out.active&&out.time!= -1))return fail(error,"invalid animation query outputs");
 out.available=out.duration>=0;return true;
}
bool Operations::inspect(const model::Capture& capture,const std::string& clip,State& out,std::string& error){
 error.clear();out={};if(!name_ok(clip))return fail(error,"clip must be 1..31 ASCII identifier characters; NULL/current are reserved");
 model::Capture current;if(!resolve(capture,current,error))return false;
 return read_state(current.model,clip,out,error);
}
bool Operations::cue(const model::Capture& capture,const std::string& clip,float rate,std::optional<float> start,State& out,std::string& error){
 error.clear();if(!std::isfinite(rate)||rate<0||rate>2)return fail(error,"animation rate must be finite in [0,2]");
 if(start&&(!std::isfinite(*start)||*start<0))return fail(error,"animation start must be finite and nonnegative");
 State before;if(!inspect(capture,clip,before,error))return false;
 if(!before.available||before.duration<=0)return fail(error,"animation clip absent or has zero duration");
 if(start&&*start>=before.duration)return fail(error,"animation start must be less than duration");
 if(before.active&&start&&std::fabs(*start-before.time)>0.001f)return fail(error,"active clip clock is preserved; seeking/restart is unsupported");
 const float begin=before.active?std::max(0.f,before.time):start.value_or(0.f);
 model::Capture current;if(!resolve(capture,current,error))return false;
 bool played=backend_->play(address(profile_->play),current.model,clip.c_str(),rate,2,begin);
 bool observed=inspect(capture,clip,out,error);
 const float expected=before.active?before.time:begin;
 const bool ok=played&&observed&&out.active&&std::fabs(out.time-expected)<=0.002f&&std::fabs(out.duration-before.duration)<=0.001f;
 std::ostringstream log;log<<"[animation] id="<<capture.id<<" model=0x"<<std::hex<<capture.model<<std::dec
  <<" clip="<<clip<<" rate="<<rate<<" time_before="<<before.time<<" time_after="<<out.time<<" duration="<<out.duration<<" verified="<<ok;
 backend_->log(log.str());
 if(!ok&&error.empty())error="animation cue/readback mismatch; controller may have replaced run";
 return ok;
}
}
