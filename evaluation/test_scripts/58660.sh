git checkout 1be39729140a6d726de164746e516c1fe5afcb19
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