cd /src/curl
git checkout dd7521bcc1b7a6fcb53c31f9bd1192fcc884bd56
apt-get update
apt-get install -y build-essential git autoconf automake libtool pkg-config perl python3 ca-certificates libssl-dev zlib1g-dev libbrotli-dev libzstd-dev libnghttp2-dev libidn2-0-dev libpsl-dev libssh2-1-dev stunnel4 openssh-server nghttp2-client
./buildconf
mkdir build-autotools && cd build-autotools
../configure --enable-debug --disable-werror --with-openssl --enable-threaded-resolver
make -j"$(nproc)"
echo "===TEST===BEGIN==="
make -j"$(nproc)" test