git checkout d84504206c420250bfe80bee25f6a59a7177c9eb
apt-get update
apt-get install -y gcc g++ libfreetype6-dev libglib2.0-dev libcairo2-dev autoconf automake libtool pkg-config ragel gtk-doc-tools cmake ninja-build build-essential libtool libtool-dev
apt-get install -y --reinstall libtool libtool-bin libglib2.0-dev libglib2.0-0 libglib2.0-bin
unset CC CXX CFLAGS CXXFLAGS LDFLAGS
git clean -fdx
./autogen.sh
export CC=gcc CXX=g++
./configure LIBS="-lpthread"
make -j"$(nproc)"
make -j"$(nproc)" check