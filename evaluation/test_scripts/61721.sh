localid=61721
git checkout b8f96b5eda5b376b05a9dbf046208388249e30a6
./configure
make -j"$(nproc)"
make -j"$(nproc)" test