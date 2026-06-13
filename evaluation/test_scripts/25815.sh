localid=25815
git checkout 58f7c31e9da3ac8cdf894307080929fa93648870
apt install -y cmake git ninja-build libicu-dev python3 zip libreadline-dev
apt-get install -y tzdata
cmake -B build -G Ninja
cmake --build ./build
cmake --build ./build --target check-hermes