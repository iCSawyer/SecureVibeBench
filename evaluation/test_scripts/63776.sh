cd /src/libredwg
git checkout 1760559320f27e75d86c9e6edab467bab63d58e9

apt-get update
apt-get install -y build-essential gcc make autoconf automake libtool pkg-config libiconv-hook-dev pcre2-utils libpcre2-dev jq texinfo doxygen valgrind parallel gperf

sh ./autogen.sh
./configure

make -j"$(nproc)"
make -j"$(nproc)" check