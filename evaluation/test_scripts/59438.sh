git checkout b17d1647cba360469ae1c22b1f7de1a3a15528b7
apt-get install -y build-essential autoconf automake libtool pkg-config zlib1g-dev libbz2-dev liblzma-dev libzstd-dev python3

autoreconf -fiv
./configure --prefix="$PWD/_inst" --disable-silent-rules
make -j"$(nproc)"
make -j"$(nproc)" check
echo $?