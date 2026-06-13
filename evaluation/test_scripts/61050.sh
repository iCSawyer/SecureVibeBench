localid=61050
git checkout 680baeffeb7983e7570b5e68db07fe47f94db8c7
git submodule update --init # if building from git to get oniguruma
autoreconf -i               # if building from git
./configure --with-oniguruma=builtin --enable-maintainer-mode
make -j"$(nproc)"
make -j"$(nproc)" check