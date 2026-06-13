git checkout 461818d4af16839b9cd8c68320fc224f66d76691

apt-get update
apt-get install -y build-essential autoconf automake libtool pkg-config libjpeg-dev libpng-dev libtiff-dev zlib1g-dev libfreetype6-dev liblcms2-dev libcups2-dev libopenjp2-7-dev python3

./autogen.sh
./configure
make -j"$(nproc)"

/src/ghostpdl/bin/gs -q -dSAFER -dBATCH -dNOPAUSE -sDEVICE=nullpage /src/ghostpdl/examples/tiger.eps && \\
/src/ghostpdl/bin/gs -q -dSAFER -dBATCH -dNOPAUSE -sDEVICE=nullpage /src/ghostpdl/examples/colorcir.ps && \\
/src/ghostpdl/bin/gs -q -dSAFER -dBATCH -dNOPAUSE -sDEVICE=nullpage /src/ghostpdl/examples/text_graphic_image.pdf && \\
echo "All smoke tests passed"