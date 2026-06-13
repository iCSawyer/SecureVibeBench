git checkout 22067c96ba2d61e6628bd1afa2ae3940c3cd46ca
apt-get install -y build-essential autoconf automake libtool pkg-config zlib1g-dev libbz2-dev liblzma-dev libzstd-dev python3

autoreconf -fiv
./configure --prefix="$PWD/_inst" --disable-silent-rules
make -j"$(nproc)"
make -j"$(nproc)" check
echo $?