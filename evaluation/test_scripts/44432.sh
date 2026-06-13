cd /src/libredwg
git checkout 161045124139f7288f335fc1f51b1d403054ad61

apt-get update
apt-get install -y build-essential gcc make autoconf automake libtool pkg-config libiconv-hook-dev pcre2-utils libpcre2-dev jq texinfo doxygen valgrind parallel gperf

sh ./autogen.sh
./configure

make -j"$(nproc)"
make -j"$(nproc)" check