cd /src/libredwg
git checkout 98034cb7f26721abaf3f2252eea84476e3c03afa

apt-get update
apt-get install -y build-essential gcc make autoconf automake libtool pkg-config libiconv-hook-dev pcre2-utils libpcre2-dev jq texinfo doxygen valgrind parallel gperf

sh ./autogen.sh
./configure

make -j"$(nproc)"
make -j"$(nproc)" check