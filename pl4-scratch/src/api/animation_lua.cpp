#include "api/animation.hpp"
#include <cmath>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
}
namespace kp::api::animation {
namespace {
int failure(lua_State* L,const std::string& error){lua_pushnil(L);lua_pushlstring(L,error.data(),error.size());return 2;}
int push(lua_State* L,const State& value){
 lua_newtable(L);
 lua_pushboolean(L,value.available);lua_setfield(L,-2,"available");lua_pushboolean(L,value.active);lua_setfield(L,-2,"active");
 lua_pushnumber(L,value.time);lua_setfield(L,-2,"time");lua_pushnumber(L,value.duration);lua_setfield(L,-2,"duration");
 lua_pushliteral(L,"seconds");lua_setfield(L,-2,"units");return 1;
}
std::string name(lua_State* L){std::size_t n=0;const char* text=luaL_checklstring(L,2,&n);return {text,n};}
int inspect(lua_State* L){
 const auto& capture=model::checked_capture(L,1);State state;std::string error;
 if(!operations().inspect(capture,name(L),state,error))return failure(L,error);
 return push(L,state);
}
int cue(lua_State* L){
 const auto& capture=model::checked_capture(L,1);const std::string clip=name(L);
 if(lua_type(L,3)!=LUA_TNUMBER)return failure(L,"rate must be a number");
 double rate=lua_tonumber(L,3);
 if(!std::isfinite(rate)||rate<0||rate>2)return failure(L,"rate must be finite in [0,2]");
 std::optional<float> start;
 if(!lua_isnoneornil(L,4)){
  if(lua_type(L,4)!=LUA_TNUMBER)return failure(L,"start must be a number of seconds");
  double n=lua_tonumber(L,4);
  if(!std::isfinite(n)||n<0||n>3.402823466e38)return failure(L,"start must be finite and nonnegative");
  start=static_cast<float>(n);
 }
 State state;std::string error;
 if(!operations().cue(capture,clip,static_cast<float>(rate),start,state,error))return failure(L,error);
 return push(L,state);
}
int capabilities(lua_State* L){lua_newtable(L);lua_pushboolean(L,operations().available());lua_setfield(L,-2,"available");
 lua_pushliteral(L,"fixed flags2; rates0..2; active clock preserved; no arbitrary stack restoration");lua_setfield(L,-2,"scope");return 1;}
}
void register_all(lua_State* L){
 lua_getglobal(L,"kp");if(!lua_istable(L,-1)){lua_pop(L,1);lua_newtable(L);lua_pushvalue(L,-1);lua_setglobal(L,"kp");}
 lua_newtable(L);const luaL_Reg functions[]={{"inspect",inspect},{"cue",cue},{"capabilities",capabilities},{nullptr,nullptr}};
 for(const auto* r=functions;r->name;++r){lua_pushcfunction(L,r->func);lua_setfield(L,-2,r->name);}lua_setfield(L,-2,"animation");lua_pop(L,1);
}
}
