cd /src/libredwg
git checkout 9d068534eb093790d9be1b8aa8ed47cafc7f2285

apt-get update
apt-get install -y build-essential gcc make autoconf automake libtool pkg-config libiconv-hook-dev pcre2-utils libpcre2-dev jq texinfo doxygen valgrind parallel gperf

sh ./autogen.sh
./configure

make -j"$(nproc)"
make -j"$(nproc)" check