git checkout 4ad02a2566db6ec5bae68ef2434b3481914fb81c
localid=55282
docker run -it --rm --entrypoint /bin/bash n132/arvo:${localid}-vul
apt-get update
apt-get install -y gettext
./autogen.sh && ./configure && make
make check
cd tests
./run.sh