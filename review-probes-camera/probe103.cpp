#include "api/camera.hpp"
#include <cstdio>
#include <stdexcept>
#include <string>
#define CHECK(x) do{if(!(x))throw std::runtime_error(#x);}while(0)
#include "tests/camera_backend_fixture.hpp"
int main(){
 const Profile& p=profiles().front();CameraFake f(p);Operations op;std::string e;Capture c;
 if(!op.bind(p.sha256,f.base,&f,e)||!op.snapshot(c,e)){std::printf("fail %s\n",e.c_str());return 1;}
 for(int i=0;i<4;++i)std::printf("raw_28[%d]=%.9g bits=%08x\n",i,c.raw_28[i],*(unsigned*)&c.raw_28[i]);
 for(int i=0;i<3;++i)std::printf("raw_38[%d]=%.9g raw_50[%d]=%.9g\n",i,c.raw_38[i],i,c.raw_50[i]);
 float a=.1f*1,b=.1f*4; std::printf("lit .1f*1=%.9g .1f*4=%.9g\n",a,b);
 std::printf("t0=%d t1=%d t2=%d t3=%d t4=%d\n",c.raw_28[0]==.1f*1,c.raw_28[3]==.1f*4,c.raw_38[0]==10.f,c.raw_38[2]==12.f,c.raw_50[1]==21.f);
 std::printf("%s\n",e.c_str());
}
