git checkout 522e7901a20dc6f2d1ceafb5d12d44f94946e11a
apt-get install -y build-essential autoconf automake libtool pkg-config zlib1g-dev libbz2-dev liblzma-dev libzstd-dev python3

autoreconf -fiv
./configure --prefix="$PWD/_inst" --disable-silent-rules
make -j"$(nproc)"
make -j"$(nproc)" check
echo $?