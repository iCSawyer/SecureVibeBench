git checkout 6903aebfddc466d966c7b865fae34572bf3ed23e

apt-get update
apt-get install -y pcscd libccid libpcsclite-dev libssl-dev libreadline-dev autoconf automake build-essential docbook-xsl xsltproc libtool pkg-config zlib1g-dev libaec-dev

./bootstrap
./configure

make -j"$(nproc)"
make -j"$(nproc)" install
make check