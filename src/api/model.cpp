#include "api/model.hpp"
#include <cmath>
#include <cstring>
#include <limits>
#include <sstream>
namespace kp::api::model {
namespace {
bool scale_ok(float n) { return std::isfinite(n) && n >= .125f && n <= 4.f; }
bool close(float a,float b) { return std::isfinite(a) && std::fabs(a-b) <= .0001f*std::fmax(1.f,std::fabs(b)); }
bool fail(std::string& error,const char* text) { error=text; return false; }
}
Operations& operations() { static Operations value;return value; }
void Operations::unbind() { backend_=nullptr; profile_=nullptr; loaded_base_=0; ++epoch_; }
Address Operations::site(unsigned i) const { return loaded_base_ + profile_->sites[i].va-profile_->preferred_base; }
bool Operations::guards(std::string& error) const {
    if (!backend_ || !profile_) return fail(error,"unsupported: no verified native model binding");
    for(unsigned i=0;i<4;++i) {
        unsigned char expected[16]{}, actual[16]{};
        const char* hex=profile_->sites[i].bytes;
        if (std::strlen(hex)!=32) return fail(error,"invalid model code guard");
        for(unsigned j=0;j<16;++j) {
            auto digit=[](char c){return c<='9'?c-'0':c-'a'+10;};
            expected[j]=static_cast<unsigned char>((digit(hex[j*2])<<4)|digit(hex[j*2+1]));
        }
        if (!backend_->read(site(i),actual,16) || std::memcmp(expected,actual,16)!=0)
            return fail(error,"unsupported: model function code guard mismatch");
    }
    return true;
}
bool Operations::bind(const std::string& sha,Address base,Backend* backend,std::string& error) {
    unbind();error.clear();
    const Profile* p=profile_for(sha);
    if (!p) return fail(error,"unsupported: unknown executable SHA256");
    if (!backend || backend->abi()!=p->abi || backend->width()!=p->width)
        return fail(error,"unsupported: model OS/ABI/pointer width mismatch");
    Address max=p->width==4?0xffffffffULL:std::numeric_limits<Address>::max();
    Address top=p->manager_slot;
    for(const auto& s:p->sites) if(s.va+16>top) top=s.va+16;
    if (!base || base>max || top-p->preferred_base>max-base)
        return fail(error,"unsupported: invalid loaded-image base/slide");
    profile_=p;backend_=backend;loaded_base_=base;
    if (!guards(error)) { unbind();return false; }
    return true;
}
bool Operations::pointer(Address address,Address& value) const {
    value=0;
    if(profile_->width==4) {std::uint32_t n=0;if(!backend_->read(address,&n,4))return false;value=n;}
    else if(!backend_->read(address,&value,8))return false;
    return value!=0;
}
bool Operations::snapshot(std::uint32_t id,Capture& out,std::string& error) {
    error.clear();out={};
    if(!guards(error))return false;
    if(id==0x7f000000)return fail(error,"invalid server object ID");
    Address manager=0,client=0,internal=0,array=0;
    if(!pointer(loaded_base_+profile_->manager_slot-profile_->preferred_base,manager) ||
       !pointer(manager+profile_->manager_client,client) || !pointer(client+profile_->client_internal,internal) ||
       !pointer(internal+profile_->internal_array,array))return fail(error,"client object array unavailable");
    std::uint8_t probe=0;
    if(!backend_->read(array,&probe,1))return fail(error,"client object array unreadable");
    std::uint32_t cid=backend_->convert(site(0),client,id);
    // The PC server ID 0x7fffffff converts to valid client ID 0xffffffff.
    // Only the engine OBJECT_INVALID value is a sentinel.
    if(cid==0x7f000000)return fail(error,"server object has no client ID");
    Address creature=backend_->creature(site(1),client,cid);
    std::uint8_t type=0;
    if(!creature || !backend_->read(creature+profile_->type_offset,&type,1) || type!=5)
        return fail(error,"client creature missing or wrong type");
    // Validate the animation span the verified getter dereferences before call.
    Address animation=0;
    if(!pointer(creature+(profile_->width==8?0x80:0x68),animation) || !backend_->read(animation,&probe,1))
        return fail(error,"creature animation unavailable");
    Address model=backend_->model(site(2),creature),guard=0,vtable=0,setter=0;
    if(!model || !pointer(model+profile_->guard_offset,guard) || !pointer(model,vtable) ||
       !pointer(vtable+profile_->scale_slot,setter) || setter!=site(3))
        return fail(error,"model missing or unsupported scale setter");
    float base=0,effective=0;
    if(!backend_->read(model+profile_->base_offset,&base,4) || !backend_->read(model+profile_->effective_offset,&effective,4) ||
       !scale_ok(base) || !std::isfinite(effective) || effective<=0)
        return fail(error,"model scale unreadable or outside checked range");
    out={epoch_,id,cid,client,creature,model,base,effective};return true;
}
bool Operations::same(const Capture& a,const Capture& b) const {
    return a.epoch==b.epoch && a.id==b.id && a.client_id==b.client_id && a.client==b.client && a.creature==b.creature && a.model==b.model;
}
bool Operations::resize(const Capture& original,float scale,Capture& after,std::string& error) {
    if(!scale_ok(scale))return fail(error,"scale must be finite and within [0.125,4]");
    Capture before;
    if(!snapshot(original.id,before,error))return false;
    if(!same(original,before))return fail(error,"stale model capture: identity changed");
    float expected=before.effective/before.base*scale;
    if(!std::isfinite(expected) || expected<=0)return fail(error,"invalid effective scale ratio");
    std::ostringstream message;
    message<<"[model] id="<<original.id<<" creature=0x"<<std::hex<<before.creature<<" model=0x"<<before.model<<std::dec
           <<" base_before="<<before.base<<" effective_before="<<before.effective<<" requested="<<scale;
    bool invoked=backend_->set_scale(site(3),before.model,scale);
    bool read=snapshot(original.id,after,error);
    bool ok=invoked && read && same(before,after) && close(after.base,scale) && close(after.effective,expected);
    message<<" setter="<<invoked<<" readback="<<read;
    if(read)message<<" base_after="<<after.base<<" effective_after="<<after.effective;
    message<<" verified="<<ok;backend_->log(message.str());
    if(!ok && error.empty())error="scale setter/readback mismatch; mutation may have occurred";
    return ok;
}
bool Operations::restore(const Capture& original,Capture& after,std::string& error) {return resize(original,original.base,after,error);}
}
