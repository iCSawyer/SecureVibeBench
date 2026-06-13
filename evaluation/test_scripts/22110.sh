localid=22110
git checkout 836740fd7829e6e3a92a766b7e559f4136378eb7
apt update
apt install -y build-essential cmake pkg-config git autoconf automake libtool \
  zlib1g-dev libpng-dev libjpeg-turbo8-dev libtiff5-dev libwebp-dev \
  libopenjp2-7-dev libgif-dev
apt install -y doxygen graphviz gnuplot
./autogen.sh
./configure
make -j"$(nproc)"
make -j1 check