git checkout 6d1fcd9cf82c6501089898066656fbe6737f3ced

apt-get update
apt-get install -y pcscd libccid libpcsclite-dev libssl-dev libreadline-dev autoconf automake build-essential docbook-xsl xsltproc libtool pkg-config zlib1g-dev libaec-dev

./bootstrap
./configure

make -j"$(nproc)"
make -j"$(nproc)" install
make check