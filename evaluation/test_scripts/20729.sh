git checkout 0717383f58e5737cc4aa28446f5a8839d484caf4
apt-get install -y build-essential autoconf automake libtool pkg-config zlib1g-dev libbz2-dev liblzma-dev libzstd-dev python3

autoreconf -fiv
./configure --prefix="$PWD/_inst" --disable-silent-rules
make -j"$(nproc)"
make -j"$(nproc)" check
echo $?