#include "api/model.hpp"
#include <cmath>
#include <cstdio>
#include <new>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
}
namespace kp::api::model {
namespace {
constexpr const char* capture_type="kp.model.capture";
constexpr std::uint64_t capture_magic=0x4b504d4f44454c31ULL;
struct Box { std::uint64_t magic; Capture value; };
int failure(lua_State* L,const std::string& error){lua_pushnil(L);lua_pushlstring(L,error.data(),error.size());return 2;}
int push(lua_State* L,const Capture& capture) {
    new(lua_newuserdata(L,sizeof(Box))) Box{capture_magic,capture};
    luaL_getmetatable(L,capture_type);lua_setmetatable(L,-2);return 1;
}
Capture& capture(lua_State* L,int index){
    if(lua_type(L,index)!=LUA_TUSERDATA || lua_objlen(L,index)!=sizeof(Box))
        luaL_argerror(L,index,"model capture allocation required");
    auto* box=static_cast<Box*>(luaL_checkudata(L,index,capture_type));
    if(box->magic!=capture_magic)luaL_argerror(L,index,"invalid model capture magic");
    return box->value;
}
int index(lua_State* L) {
    const Capture& c=capture(L,1);const char* key=luaL_checkstring(L,2);
    std::string name(key);
    if(name=="base")lua_pushnumber(L,c.base);
    else if(name=="effective")lua_pushnumber(L,c.effective);
    else if(name=="id")lua_pushnumber(L,c.id);
    else if(name=="model" || name=="creature") {
        char text[32];std::snprintf(text,sizeof(text),"0x%llx",static_cast<unsigned long long>(name=="model"?c.model:c.creature));lua_pushstring(L,text);
    } else lua_pushnil(L);
    return 1;
}
int snapshot(lua_State* L) {
    if(lua_type(L,1)!=LUA_TNUMBER)return failure(L,"server ID must be an exact uint32 number");
    double id=lua_tonumber(L,1);
    if(!std::isfinite(id) || id<0 || id>4294967295. || std::floor(id)!=id)return failure(L,"server ID must be an exact uint32 number");
    Capture result;std::string error;
    if(!operations().snapshot(static_cast<std::uint32_t>(id),result,error))return failure(L,error);
    return push(L,result);
}
int resize(lua_State* L) {
    const Capture& c=capture(L,1);
    if(lua_type(L,2)!=LUA_TNUMBER)return failure(L,"scale must be numeric");
    double scale=lua_tonumber(L,2);
    if(!std::isfinite(scale) || scale<.125 || scale>4.)return failure(L,"scale must be finite and within [0.125,4]");
    Capture result;std::string error;
    if(!operations().resize(c,static_cast<float>(scale),result,error))return failure(L,error);
    return push(L,result);
}
int restore(lua_State* L) {
    Capture result;std::string error;
    if(!operations().restore(capture(L,1),result,error))return failure(L,error);
    return push(L,result);
}
int capabilities(lua_State* L) {
    lua_newtable(L);lua_pushboolean(L,operations().available());lua_setfield(L,-2,"available");
    const auto* p=operations().profile();
    lua_pushstring(L,p?p->name:"unsupported");lua_setfield(L,-2,"profile");
    lua_pushstring(L,p?abi_name(p->abi):"no verified host binding");lua_setfield(L,-2,"abi");
    lua_pushstring(L,"exact address reuse cannot be detected; Darwin loader/live validation absent");lua_setfield(L,-2,"limits");
    lua_pushnumber(L,.125);lua_setfield(L,-2,"min_scale");lua_pushnumber(L,4);lua_setfield(L,-2,"max_scale");
    return 1;
}
}
void register_all(lua_State* L) {
    luaL_newmetatable(L,capture_type);lua_pushcfunction(L,index);lua_setfield(L,-2,"__index");
    lua_pushliteral(L,"protected model capture");lua_setfield(L,-2,"__metatable");lua_pop(L,1);
    lua_getglobal(L,"kp");if(!lua_istable(L,-1)){lua_pop(L,1);lua_newtable(L);lua_pushvalue(L,-1);lua_setglobal(L,"kp");}
    lua_newtable(L);
    static const luaL_Reg functions[]={{"snapshot",snapshot},{"resize",resize},{"restore",restore},{"capabilities",capabilities},{nullptr,nullptr}};
    for(const luaL_Reg* r=functions;r->name;++r) {
        lua_pushcfunction(L,r->func);lua_setfield(L,-2,r->name);
    }
    lua_setfield(L,-2,"model");lua_pop(L,1);
}
}
