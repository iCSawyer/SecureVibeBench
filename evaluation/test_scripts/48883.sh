cd /src/ndpi
git checkout 1a01e8dc687df706ef775122a5bc31baa07f12d4
apt-get update && apt-get install -y build-essential git gettext flex bison libtool autoconf automake pkg-config libpcap-dev libjson-c-dev libnuma-dev libpcre2-dev libmaxminddb-dev librrd-dev

./autogen.sh

make -j"$(nproc)"
make -j"$(nproc)" check