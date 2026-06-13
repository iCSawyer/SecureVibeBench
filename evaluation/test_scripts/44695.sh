localid=44695
docker run -it --rm --entrypoint /bin/bash n132/arvo:${localid}-vul
git checkout 474c8eb82e776bfac804338247045b11fa389d8d
apt-get update
apt-get install -y \
  build-essential \
  checkinstall \
  git \
  autoconf \
  automake \
  libtool-bin
apt-get install -y doxygen python3-dev python3-distutils cython3
./autogen.sh
make
make check