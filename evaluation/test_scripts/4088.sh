git checkout a6150306838b168475a9aa661ad569b0405c9f91
apt-get install -y gcc g++ libfreetype6-dev libglib2.0-dev libcairo2-dev autoconf automake libtool pkg-config ragel gtk-doc-tools cmake ninja-build build-essential
unset CC CXX CFLAGS CXXFLAGS LDFLAGS
git clean -fdx
./autogen.sh
./configure
make -j"$(nproc)"
make -j"$(nproc)" check