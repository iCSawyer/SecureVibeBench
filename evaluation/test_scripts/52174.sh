cd /src/ndpi
git checkout 199c86e3df8da0b4734193df8424cd4a62768ae8
apt-get update && apt-get install -y build-essential git gettext flex bison libtool autoconf automake pkg-config libpcap-dev libjson-c-dev libnuma-dev libpcre2-dev libmaxminddb-dev librrd-dev

./autogen.sh

make -j"$(nproc)"
make -j"$(nproc)" check