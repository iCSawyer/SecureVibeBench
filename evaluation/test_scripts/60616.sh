git checkout 88880db0307a07e33cf2e1592bb029e9c170dfea

apt-get update
apt-get install -y pcscd libccid libpcsclite-dev libssl-dev libreadline-dev autoconf automake build-essential docbook-xsl xsltproc libtool pkg-config zlib1g-dev libaec-dev

./bootstrap
./configure

make -j"$(nproc)"
make -j"$(nproc)" install
make check