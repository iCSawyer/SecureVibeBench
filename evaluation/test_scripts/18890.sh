git checkout 0977b5496ad7f35f6575555714e2c352ce85285e

apt-get update
apt-get install -y pcscd libccid libpcsclite-dev libssl-dev libreadline-dev autoconf automake build-essential docbook-xsl xsltproc libtool pkg-config zlib1g-dev libaec-dev

./bootstrap
./configure

make -j"$(nproc)"
make -j"$(nproc)" install
make check