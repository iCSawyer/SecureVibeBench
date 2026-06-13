localid=57369
cd ndpi
git checkout 530d0de4382ab4d70cfc1dedcf8cf2ac729dfddf
export DEBIAN_FRONTEND=noninteractive
apt-get update && apt-get install -y build-essential git gettext flex bison libtool autoconf automake pkg-config libpcap-dev libjson-c-dev libnuma-dev libpcre2-dev libmaxminddb-dev librrd-dev

./autogen.sh

make
make check