#include "hooks/lua_bridge.hpp"
#include "platform/platform.hpp"
#include <algorithm>
#include <cmath>
#include <cstring>
#include <limits>
#include <map>
#include <memory>
extern "C" {
#include "lua.h"
#include "lauxlib.h"
}

namespace kp::hooks::lua_bridge {
namespace {
struct Handler { lua_State* state; int ref; unsigned id; bool post, removed; };
struct Node { Entry entry; std::vector<Handler> handlers; };
std::map<std::string,std::unique_ptr<Node>> nodes;
const AddressTable* table=nullptr;
std::uintptr_t runtime_base=0;
Entry::Gate live_gate=nullptr, patch_gate=nullptr;
Guard guard=nullptr;
Review review=nullptr;
OnError on_error=nullptr;
unsigned next_id=0;
unsigned dispatch_depth=0;
struct View { HookCtx* ctx; Entry* entry; };
struct Handle { unsigned id; };
constexpr const char* view_meta="kp.hook.context";
constexpr const char* handle_meta="kp.hook.handle";
constexpr const char* state_meta="kp.hook.state.metatable";

View* view(lua_State* L, int idx=1) {
    auto* v=static_cast<View*>(luaL_checkudata(L,idx,view_meta));
    if (!v->ctx) luaL_error(L,"hook context has expired");
    return v;
}
bool unsigned_type(const std::string& t) {
    return t.find("unsigned")!=std::string::npos || t.find("uint")!=std::string::npos ||
        t.find("undefined")!=std::string::npos || t.find('*')!=std::string::npos ||
        t=="DWORD" || t=="WORD" || t=="BYTE" || t=="ulong" || t=="ushort" ||
        t=="uchar" || t=="size_t";
}
bool address_type(const std::string& t) { return t=="address" || t=="cexostring_ptr"; }
int width_for(const std::string& t, int size) {
    if (t=="char" || t=="signed char" || t=="unsigned char" || t=="int8_t" || t=="uint8_t") return 1;
    if (t=="short" || t=="unsigned short" || t=="int16_t" || t=="uint16_t") return 2;
    return size;
}
double checked_number(lua_State* L,int idx) {
    if (lua_type(L,idx)!=LUA_TNUMBER) luaL_error(L,"hook value must be a number");
    double n=lua_tonumber(L,idx);
    if (!std::isfinite(n)) luaL_error(L,"hook value must be finite");
    return n;
}
void push_scalar(lua_State* L,const void* ptr,int size,const std::string& type,const std::string& kind) {
    if (kind=="number") {
        if(size==4) { float f; std::memcpy(&f,ptr,4); lua_pushnumber(L,f); }
        else { double d; std::memcpy(&d,ptr,8); lua_pushnumber(L,d); }
        return;
    }
    std::uint64_t bits=0; std::memcpy(&bits,ptr,size);
    double n;
    if(unsigned_type(type)||address_type(kind)) n=static_cast<double>(bits);
    else {
        std::int64_t signed_bits=static_cast<std::int64_t>(bits);
        if(size<8 && (bits & (std::uint64_t(1)<<(size*8-1)))) signed_bits-=std::int64_t(1)<<(size*8);
        n=static_cast<double>(signed_bits);
    }
    if(size==8 && (n>9007199254740991.0 || n< -9007199254740991.0))
        luaL_error(L,"64-bit hook value exceeds Lua exact integer range");
    lua_pushnumber(L,n);
}
void put_scalar(lua_State* L,int idx,void* ptr,int size,const std::string& type,const std::string& kind) {
    double n=checked_number(L,idx);
    if(kind=="number") {
        if(size==4) {
            if(std::fabs(n)>std::numeric_limits<float>::max()) luaL_error(L,"float argument out of range");
            float f=static_cast<float>(n); std::memcpy(ptr,&f,4);
        } else std::memcpy(ptr,&n,8);
        return;
    }
    const int width=width_for(type,size);
    const bool u=unsigned_type(type)||address_type(kind);
    double lo=u?0:-std::ldexp(1.0,width*8-1);
    double hi=u?std::ldexp(1.0,width*8)-1:std::ldexp(1.0,width*8-1)-1;
    if(size==8) {lo=std::max(lo,-9007199254740991.0); hi=std::min(hi,9007199254740991.0);}
    if(type=="bool") {lo=0;hi=1;}
    if(std::floor(n)!=n || n<lo || n>hi) luaL_error(L,"hook integer out of range");
    std::uint64_t bits=u?static_cast<std::uint64_t>(n):static_cast<std::uint64_t>(static_cast<std::int64_t>(n));
    std::memcpy(ptr,&bits,size);
}
const AbiParam* param(lua_State* L,View* v) {
    double n=checked_number(L,2);
    if(n<1 || n>2147483647 || std::floor(n)!=n) luaL_error(L,"argument index must be a positive integer");
    for(const auto& p:v->entry->site.abi.params) if(p.index==static_cast<int>(n)-1) return &p;
    luaL_error(L,"argument index is not in manifest"); return nullptr;
}
void* slot(View* v,const AbiParam& p) {
    if(p.reg=="ECX") return &v->ctx->ecx;
    if(p.reg=="EDX") return &v->ctx->edx;
    return reinterpret_cast<unsigned char*>(v->ctx->args)+p.stack-4;
}
int args_read(lua_State* L) {
    auto* v=view(L,lua_upvalueindex(1)); const auto* p=param(L,v);
    push_scalar(L,slot(v,*p),p->size,p->c_type,p->lua); return 1;
}
int args_write(lua_State* L) {
    auto* v=view(L,lua_upvalueindex(1));
    if(v->ctx->post || !v->entry->site.abi.rewrite) return luaL_error(L,"argument rewrite is not permitted");
    const auto* p=param(L,v); put_scalar(L,3,slot(v,*p),p->size,p->c_type,p->lua); return 0;
}
void get_return(lua_State* L,View* v) {
    const auto& a=v->entry->site.abi;
    if(a.ret_storage=="void") lua_pushnil(L);
    else if(a.ret_storage=="ST0") {
        long double n=0; std::memcpy(&n,v->ctx->st0,10); lua_pushnumber(L,static_cast<double>(n));
    } else push_scalar(L,&v->ctx->eax,a.ret_storage=="EDX:EAX"?8:4,a.ret_type,a.ret_lua);
}
void set_return(lua_State* L,View* v,int idx) {
    const auto& a=v->entry->site.abi;
    if(a.ret_storage=="void") {if(!lua_isnil(L,idx)) luaL_error(L,"void return requires nil");}
    else if(a.ret_storage=="ST0") {
        long double n=checked_number(L,idx); std::memcpy(v->ctx->st0,&n,10);
    } else put_scalar(L,idx,&v->ctx->eax,a.ret_storage=="EDX:EAX"?8:4,a.ret_type,a.ret_lua);
}
int skip(lua_State* L) {
    auto* v=view(L);
    if(v->ctx->post || !v->entry->site.abi.skip) return luaL_error(L,"skip is not permitted for this hook");
    set_return(L,v,2); v->ctx->skip=true; return 0;
}
int ctx_read(lua_State* L) {
    auto* v=view(L); const char* key=luaL_checkstring(L,2);
    if(!std::strcmp(key,"this")) {
        if(v->entry->site.abi.this_reg.empty()) lua_pushnil(L); else lua_pushnumber(L,v->ctx->ecx);
    } else if(!std::strcmp(key,"args")) {
        lua_newtable(L); lua_newtable(L);
        lua_pushvalue(L,1); lua_pushcclosure(L,args_read,1); lua_setfield(L,-2,"__index");
        lua_pushvalue(L,1); lua_pushcclosure(L,args_write,1); lua_setfield(L,-2,"__newindex");
        lua_pushboolean(L,0);lua_setfield(L,-2,"__metatable"); lua_setmetatable(L,-2);
    } else if(!std::strcmp(key,"skip")) lua_pushcfunction(L,skip);
    else if(!std::strcmp(key,"ret")) {
        if(!v->ctx->post) return luaL_error(L,"return is only readable in post hooks");
        get_return(L,v);
    } else lua_pushnil(L);
    return 1;
}
int ctx_write(lua_State* L) {
    auto* v=view(L);const char* key=luaL_checkstring(L,2);
    if(!std::strcmp(key,"this")) {
        if(v->ctx->post || !v->entry->site.abi.rewrite || v->entry->site.abi.this_reg.empty()) return luaL_error(L,"this rewrite is not permitted");
        double n=checked_number(L,3);
        if(n<0 || n>4294967295.0 || std::floor(n)!=n) return luaL_error(L,"this address out of range");
        v->ctx->ecx=static_cast<std::uint32_t>(n);
    } else if(!std::strcmp(key,"ret")) {
        if(!v->ctx->post || !v->entry->site.abi.override_return) return luaL_error(L,"return override is not permitted");
        set_return(L,v,3);
    } else return luaL_error(L,"unknown or read-only hook context field");
    return 0;
}
struct Call { lua_State* state; int ref; Entry* entry; HookCtx* ctx; View* view=nullptr; int status=-1; int root=LUA_NOREF; };
int invoke(lua_State* L) {
    auto* c=static_cast<Call*>(lua_touserdata(L,1));
    lua_rawgeti(L,LUA_REGISTRYINDEX,c->ref);
    auto* v=static_cast<View*>(lua_newuserdata(L,sizeof(View)));
    *v={c->ctx,c->entry}; c->view=v;
    luaL_getmetatable(L,view_meta);lua_setmetatable(L,-2);
    // Keep the view rooted even if the handler discards its argument and runs GC.
    lua_pushvalue(L,-1);c->root=luaL_ref(L,LUA_REGISTRYINDEX);
    lua_call(L,1,0); return 0;
}
void run(void* raw) {
    auto* c=static_cast<Call*>(raw); auto* L=c->state;
    lua_pushcfunction(L,invoke);lua_pushlightuserdata(L,c);
    c->status=lua_pcall(L,1,0,0);
}
bool dispatch(void* user,Entry& entry,HookCtx& ctx,bool post) {
    auto& n=*static_cast<Node*>(user);
    ++dispatch_depth;
    for(auto& h:n.handlers) {
        if(h.removed || h.post!=post || h.state==nullptr) continue;
        const HookCtx before_handler = ctx;
        int top=lua_gettop(h.state);
        Call c{h.state,h.ref,&entry,&ctx};
        bool healthy=guard && guard(entry,run,&c);
        if(!healthy) {
            entry.poisoned.store(true,std::memory_order_release);
            // A fault may leave the Lua VM internally inconsistent. Do not call
            // ANY Lua API on it here; the host guard disables scripting globally.
            if(c.view) c.view->ctx=nullptr;
            --dispatch_depth; return false;
        }
        if(c.view) c.view->ctx=nullptr;
        if(c.status) {
            ctx = before_handler;
            const char* err_msg=lua_tostring(h.state,-1)?lua_tostring(h.state,-1):"handler failed";
            platform::log(platform::LogLevel::Warn,"Lua hook %s: %s",entry.site.name.c_str(),err_msg);
            const bool quarantined = on_error && on_error(h.state,entry.site.name.c_str(),err_msg);
            lua_settop(h.state,top);
            luaL_unref(h.state,LUA_REGISTRYINDEX,c.root);
            if(quarantined) {
                h.removed=true;
                luaL_unref(h.state,LUA_REGISTRYINDEX,h.ref);
                h.state=nullptr;
                h.ref=LUA_NOREF;
            }
            if(!on_error) {--dispatch_depth;return false;}
            continue;
        }
        lua_settop(h.state,top);
        luaL_unref(h.state,LUA_REGISTRYINDEX,c.root);
    }
    --dispatch_depth; return true;
}
int remove(lua_State* L) {
    const auto* handle=static_cast<Handle*>(luaL_checkudata(L,1,handle_meta));
    for(auto& item:nodes) for(auto& h:item.second->handlers) if(h.id==handle->id && h.state==L && !h.removed) {
        h.removed=true;luaL_unref(L,LUA_REGISTRYINDEX,h.ref);h.ref=LUA_NOREF;
    }
    return 0;
}
// No C++ owning objects may be live across luaL_error's longjmp.
bool install_node(const char* id,Node*& out,std::string& error) {
    auto it=nodes.find(id); if(it!=nodes.end()) {out=it->second.get();return true;}
    const auto* s=table?table->find(id):nullptr;
    if(!s) {error="unknown site";return false;}
    if(!review || !review(*s)) {error="site lacks explicit reviewed-ABI opt-in";return false;}
    if(!s->resolved || s->addr==0) {error="site is unresolved: "+s->locate_error;return false;}
    error=refusal(*s);if(!error.empty())return false;
    auto node=std::make_unique<Node>();out=node.get();
    auto delta=runtime_base?runtime_base-table->image_base():0;
    if(!node->entry.install(*s,s->addr+delta,dispatch,out,live_gate,error)) {out=nullptr;return false;}
    nodes.emplace(id,std::move(node));return true;
}
int add(lua_State* L) {
    const char* id=luaL_checkstring(L,1);luaL_checktype(L,2,LUA_TFUNCTION);
    lua_getfield(L,LUA_REGISTRYINDEX,"kp.hook.state");
    auto** owner=static_cast<lua_State**>(lua_touserdata(L,-1));
    const bool owner_thread=owner && *owner==L;lua_pop(L,1);
    if(!owner_thread) return luaL_error(L,"hooks must be registered from their owning Lua state, not a coroutine");
    bool post=lua_toboolean(L,lua_upvalueindex(1));
    if(dispatch_depth) return luaL_error(L,"cannot register a hook during hook dispatch");
    if(!table || !guard || !patch_gate || !patch_gate()) return luaL_error(L,"hook installation requires a quiescent engine-thread point");
    const auto* s=table->find(id);
    if(!s) return luaL_error(L,"hook %s refused: unknown site",id);
    if(post?!s->abi.post:!s->abi.pre) return luaL_error(L,"hook %s refused: phase disabled by manifest",id);
    Node* n=nullptr;
    bool ok;
    {std::string error;ok=install_node(id,n,error);if(!ok)lua_pushfstring(L,"hook %s refused: %s",id,error.c_str());}
    if(!ok)return lua_error(L);
    lua_pushvalue(L,2);int ref=luaL_ref(L,LUA_REGISTRYINDEX);
    unsigned id_num=++next_id;
    n->handlers.push_back({L,ref,id_num,post,false});
    auto* h=static_cast<Handle*>(lua_newuserdata(L,sizeof(Handle)));h->id=id_num;
    luaL_getmetatable(L,handle_meta);lua_setmetatable(L,-2);return 1;
}
int state_gc(lua_State* L) {
    // LuaJIT may execute __gc on its dedicated finalizer thread, not the
    // lua_State that registered handlers. Close the stored owner identity.
    auto** owner=static_cast<lua_State**>(lua_touserdata(L,1));
    if(owner && *owner) {close_state(*owner);*owner=nullptr;}
    return 0;
}
}
void bind(const AddressTable* t,std::uintptr_t base,Entry::Gate live,Entry::Gate patch,Guard g,Review r,OnError e) {
    table=t;runtime_base=base;live_gate=live;patch_gate=patch;guard=g;review=r;on_error=e;
}
void close_state(lua_State* L) {
    for(auto& item:nodes) for(auto& h:item.second->handlers) if(h.state==L) {
        h.removed=true;h.state=nullptr;h.ref=LUA_NOREF;
    }
}
void shutdown() {
    // The owner calls this at shutdown, after disabling dispatch and before
    // releasing the manifest. Removed handlers leave detours until this point.
    for(auto it=nodes.begin();it!=nodes.end();) {
        if(it->second->entry.uninstall()) it=nodes.erase(it);else ++it;
    }
    table=nullptr;live_gate=patch_gate=nullptr;guard=nullptr;review=nullptr;on_error=nullptr;
}
void register_all(lua_State* L) {
    int top=lua_gettop(L);
    luaL_newmetatable(L,view_meta);
    lua_pushcfunction(L,ctx_read);lua_setfield(L,-2,"__index");
    lua_pushcfunction(L,ctx_write);lua_setfield(L,-2,"__newindex");
    lua_pushboolean(L,0);lua_setfield(L,-2,"__metatable");lua_pop(L,1);
    luaL_newmetatable(L,handle_meta);lua_pushvalue(L,-1);lua_setfield(L,-2,"__index");
    lua_pushcfunction(L,remove);lua_setfield(L,-2,"remove");lua_pop(L,1);
    luaL_newmetatable(L,state_meta);lua_pushcfunction(L,state_gc);lua_setfield(L,-2,"__gc");lua_pop(L,1);
    lua_getfield(L,LUA_REGISTRYINDEX,"kp.hook.state");
    if(lua_isnil(L,-1)) {
        lua_pop(L,1);auto** owner=static_cast<lua_State**>(lua_newuserdata(L,sizeof(lua_State*)));
        *owner=L;luaL_getmetatable(L,state_meta);lua_setmetatable(L,-2);
        lua_setfield(L,LUA_REGISTRYINDEX,"kp.hook.state");
    } else lua_pop(L,1);
    lua_getglobal(L,"kp");if(!lua_istable(L,-1)) {
        lua_pop(L,1);lua_newtable(L);lua_pushvalue(L,-1);lua_setglobal(L,"kp");
    }
    lua_newtable(L);
    lua_pushboolean(L,0);lua_pushcclosure(L,add,1);lua_setfield(L,-2,"pre");
    lua_pushboolean(L,1);lua_pushcclosure(L,add,1);lua_setfield(L,-2,"post");
    lua_setfield(L,-2,"hook");lua_settop(L,top);
}
} // namespace kp::hooks::lua_bridge
