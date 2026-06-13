git checkout 86b4fe5b45458c65f26762fb1de2803056e3d37e
apt update
apt install -y build-essential git
make
make -C tests datagen
ZSTD_BIN="$(pwd)/programs/zstd" \
DATAGEN_BIN="$(pwd)/tests/datagen" \
./tests/playTests.sh
make -C tests fullbench && ./tests/fullbench
make -C tests zstreamtest && ./tests/zstreamtest