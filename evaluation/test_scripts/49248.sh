git checkout 972d3292eee44e9b4c61769365a3ec651ec18f39

apt-get update
apt-get install -y pcscd libccid libpcsclite-dev libssl-dev libreadline-dev autoconf automake build-essential docbook-xsl xsltproc libtool pkg-config zlib1g-dev libaec-dev

./bootstrap
./configure

make -j"$(nproc)"
make -j"$(nproc)" install
make check