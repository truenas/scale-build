# truenas-build

A build framework for TrueNAS SCALE

## Requirements

Any Debian 10 or later host, or TrueNAS SCALE image itself. In addition to the host, you will want to pre-install the following CLI tools:

* debootstrap
* jq
* git
* xorriso
* grub-mkrescue
* mformat
* mksquashfs


## Usage

After the pre-requistes are installed, simply run "make" (as root or sudo) to perform a complete build which performs the following steps:

``` make checkout ```

Pulls in the latest target source repos from online. Re-run to update to latest sources at any time.

``` make packages ```

Builds all the *.deb packages from the checked out source repos and stages them for further stages.

``` make update ```

Builds the stand-alone update file, used for online/offline updating or building ISO images

``` make iso ```

Builds the ISO image for fresh installation


