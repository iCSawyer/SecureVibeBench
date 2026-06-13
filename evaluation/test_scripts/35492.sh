git checkout 982ec302b67f3c7f8df667dadb67352b1e4a6d18
localid=35492
docker run -it --rm --entrypoint /bin/bash n132/arvo:${localid}-vul
apt-get install --no-install-recommends --no-install-suggests \
    bison \
    flex \
    gawk \
    gcc \
    gettext \
    make \
    libaudit-dev \
    libbz2-dev \
    libcap-dev \
    libcap-ng-dev \
    libcunit1-dev \
    libglib2.0-dev \
    libpcre2-dev \
    pkgconf \
    python3 \
    systemd \
    xmlto -y
apt-get install --no-install-recommends --no-install-suggests \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    ruby-dev \
    swig -y

make clean distclean
make DESTDIR=~/obj install install-rubywrap install-pywrap
make install install-pywrap relabel
DESTDIR=~/obj ./scripts/env_use_destdir make test