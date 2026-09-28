#pragma once
#include "api/model.hpp"
#include <optional>
namespace kp::api::animation {
using model::Address;
struct Site {Address va;const char* bytes;int rebased_u32=-1;};
struct Profile {const char* model_profile;Site play,query;};
const std::array<Profile,4>& profiles();
struct State {bool available=false,active=false;float time=-1,duration=-1;};
struct Backend {
    virtual ~Backend()=default;
    virtual model::Abi abi()const=0;
    virtual unsigned width()const=0;
    virtual bool read(Address,void*,std::size_t)const=0;
    virtual bool query(Address function,Address model,const char* name,float& time,float& duration)=0;
    virtual bool play(Address function,Address model,const char* name,float rate,int flags,float start)=0;
    virtual void log(const std::string&)=0;
};
class Operations {
public:
    bool bind(const std::string& sha,Address loaded_base,model::Operations*,Backend*,std::string&);
    void unbind();
    bool available()const{return backend_!=nullptr;}
    bool inspect(const model::Capture&,const std::string& clip,State&,std::string&);
    // Omitted start preserves an existing run clock, or starts a new run at0.
    // Seeking an active run is refused; force-new/restart flags are not exposed.
    bool cue(const model::Capture&,const std::string&,float rate,std::optional<float> start,State&,std::string&);
private:
    bool guards(std::string&)const;
    bool resolve(const model::Capture&,model::Capture&,std::string&)const;
    bool read_state(Address,const std::string&,State&,std::string&);
    Address address(const Site&)const;
    const Profile* profile_=nullptr;const model::Profile* model_profile_=nullptr;
    Address loaded_base_=0;model::Operations* models_=nullptr;Backend* backend_=nullptr;
};
Operations& operations();
bool bind_native(const std::string& sha,Address loaded_base,model::Reader,model::Logger,void*,std::string&);
void register_all(lua_State*);
}
