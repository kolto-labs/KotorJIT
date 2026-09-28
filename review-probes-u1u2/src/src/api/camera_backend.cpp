#include "api/camera.hpp"
namespace kp::api::camera {
Backend* native_backend(model::Reader,void*){return nullptr;}
bool bind_native(const std::string&,Address,model::Reader,void*,std::string& e){e="unsupported: stub";return false;}
}
