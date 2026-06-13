cd /src/ndpi
git checkout 66bee475ae1b1f4b1b4104555b7bb4d38c3e20b6
apt-get update && apt-get install -y build-essential git gettext flex bison libtool autoconf automake pkg-config libpcap-dev libjson-c-dev libnuma-dev libpcre2-dev libmaxminddb-dev librrd-dev

./autogen.sh

make -j"$(nproc)"
make -j"$(nproc)" check