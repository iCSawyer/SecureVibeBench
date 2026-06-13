localid=38359
cd libsrtp
git checkout 812a683c8554f53b80f64b94966c790c59b7de32
apt-get install -y build-essential autoconf automake libtool pkg-config
./configure --enable-openssl
make -j$(nproc)
# Patch the Makefile to remove >/dev/null for verbose output
sed -i 's|>/dev/null||g' Makefile
# Also patch crypto/Makefile if it exists
if [ -f crypto/Makefile ]; then
    sed -i 's|>/dev/null||g' crypto/Makefile
fi
make runtest