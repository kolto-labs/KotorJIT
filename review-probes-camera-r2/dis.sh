d(){ objdump -D -b binary -m i386 -M intel --adjust-vma=0x400000 --start-address=$1 --stop-address=$2 /home/brunner56/biodecompwarehouse/kotorxid/output/binaries/K1__k1_win_gog_swkotor.exe/artifacts/raw_image | grep -E "^ +[0-9a-f]+:" ; }
echo "== ctor"; d 0x639fd0 0x63a034
echo "== copy-ctor"; d 0x63ad80 0x63add2
for a in 0x5f6036 0x60b93a 0x615b60; do echo "== $a"; d $a $((a+0x18)); done
