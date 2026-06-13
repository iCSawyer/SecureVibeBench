git checkout 9b0b40b3c1ac8155c80ed5dc976228f4d3ec7e1f
apt-get install -y gcc g++ libfreetype6-dev libglib2.0-dev libcairo2-dev autoconf automake libtool pkg-config ragel gtk-doc-tools cmake ninja-build build-essential
unset CC CXX CFLAGS CXXFLAGS LDFLAGS
git clean -fdx
./autogen.sh
./configure
make -j"$(nproc)"
make -j"$(nproc)" check