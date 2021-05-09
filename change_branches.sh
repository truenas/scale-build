#!/bin/sh


branch="master"
cd /mnt/evo/build

for i in "truenas" "truenas_files" "middlewared"; do
	echo "\nupdating $i"
	git -C sources/"$i" fetch origin
	git -C sources/"$i" checkout "$branch"
	git -C sources/"$i" reset --hard origin/"$branch"
done
