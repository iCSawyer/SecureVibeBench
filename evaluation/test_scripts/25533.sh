localid=25533
git checkout 3ac8a04f8f6071be0901a9ddcda296f58b2bcf0c
autoreconf -i
./configure
make
make -j$(nproc) test