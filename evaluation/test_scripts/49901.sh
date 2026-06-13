cd /src/ndpi
git checkout 346e274a1b1d713aedfc341f7d1300009f9f0e1a
apt-get update && apt-get install -y build-essential git gettext flex bison libtool autoconf automake pkg-config libpcap-dev libjson-c-dev libnuma-dev libpcre2-dev libmaxminddb-dev librrd-dev

./autogen.sh

make -j"$(nproc)"
make -j"$(nproc)" check