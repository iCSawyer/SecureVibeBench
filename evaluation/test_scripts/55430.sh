localid=55430
git checkout b0ac20b2f251f0ab6ba14260609af3564352adaf
git submodule update --init --recursive
apt-get update
apt-get install -y swig flex bison
apt-get install -y libc++-dev libc++abi-dev
./configure && make && sudo make install
make test