cd /src/mruby
git checkout b1b9b157f85fe371db706e0c11024681d84e4aba

apt install -y build-essential ruby rake git bison gperf

rake -j"$(nproc)"
rake test --verbose