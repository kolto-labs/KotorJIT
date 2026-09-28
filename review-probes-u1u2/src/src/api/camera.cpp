#include "api/camera.hpp"
// RED STUB: replaced by the checked core.
namespace kp::api::camera {
Operations& operations(){static Operations o;return o;}
void Operations::unbind(){backend_=nullptr;profile_=nullptr;loaded_base_=0;++epoch_;}
bool Operations::fail(Failure f,std::string& e,const std::string& t){failure_=f;e=t;return false;}
bool Operations::valid_span(const Span&){return false;}
bool Operations::guards(std::string& e){return fail(Failure::Unsupported,e,"unsupported: stub");}
bool Operations::pointer(Address,Address&)const{return false;}
bool Operations::bind(const std::string&,Address,Backend*,std::string& e){unbind();return fail(Failure::Unsupported,e,"unsupported: stub");}
bool Operations::snapshot(Capture&,std::string& e){return fail(Failure::Unsupported,e,"unsupported: stub");}
}
