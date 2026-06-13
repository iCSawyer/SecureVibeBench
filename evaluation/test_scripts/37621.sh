localid=37621
cd lua
git checkout 41871f1803770305f182f56cbd22a336c5236a19
make PLAT=linux
cd testes/libs
make
cd ..
cat /dev/null | ../lua all.lua