git checkout c1306126c3f12c16ad62dd2553132f64a28ca607
apt-get install -y build-essential autoconf automake libtool pkg-config cmake ninja-build valgrind

./autogen.sh
./configure --prefix="$PWD/_inst" --enable-pcre2-16 --enable-pcre2-32 --enable-jit

make -j"$(nproc)"
make check