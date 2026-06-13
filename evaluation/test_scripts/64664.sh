localid=64664
git checkout 81dd97bd5612846411b581bed5b8e02b624f1160
apt-get update
apt-get install -y build-essential
apt-get install -y xorg-dev mesa-common-dev libgl1-mesa-dev libglu1-mesa-dev \
                        libxcursor-dev libxrandr-dev libxinerama-dev
make prefix=/usr/local install
wget https://ontheline.trincoll.edu/images/bookdown/sample-local-pdf.pdf
mutool info sample-local-pdf.pdf
echo $?