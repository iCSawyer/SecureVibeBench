git checkout f7c0b4319c6f82f1e0020a0029469d8953a7a161
apt-get install -y gcc g++ libfreetype6-dev libglib2.0-dev libcairo2-dev autoconf automake libtool pkg-config ragel gtk-doc-tools cmake ninja-build build-essential
unset CC CXX CFLAGS CXXFLAGS LDFLAGS
git clean -fdx
./autogen.sh
./configure
make -j"$(nproc)"
make -j"$(nproc)" check