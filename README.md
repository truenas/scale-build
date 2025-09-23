<p align="center">
 <a href="https://discord.gg/Q3St5fPETd"><img alt="Join Discord" src="https://badgen.net/discord/members/Q3St5fPETd/?icon=discord&label=Join%20the%20TrueNAS%20Community" /></a>
 <a href="https://www.truenas.com/community/"><img alt="Join Forums" src="https://badgen.net/badge/Forums/Post%20Now//purple" /></a> 
 <a href="https://jira.ixsystems.com"><img alt="File Issue" src="https://badgen.net/badge/Jira/File%20Issue//red?icon=jira" /></a>
</p>

# truenas-build

A build framework for TrueNAS SCALE.

Found an issue in the build for SCALE? Please report it on our [Jira bugtracker](https://jira.ixsystems.com).

## Requirements

 - Supported version of Debian
 - Python 3.11 or later
 - 20GB of RAM
 - At least 15GB of free disk space

In addition to the host, you will want to pre-install the following packages:

* build-essential
* debootstrap
* libjson-perl
* git
* python3-pip
* python3-venv
* squashfs-tools
* rsync
* unzip
* libarchive-tools

``` % sudo apt install build-essential debootstrap git python3-pip python3-venv squashfs-tools unzip libjson-perl rsync libarchive-tools```

## Usage

The build system automatically manages a Python virtual environment to ensure build consistency. It detects changes in the git repository hash and automatically recreates the virtual environment when needed, ensuring that the build tools are always in sync with the current codebase.

After the pre-requistes are installed, simply run "make" (as root or sudo) to perform a complete build which performs the following steps:

``` make checkout ```

Pulls in the latest target source repos from online. Re-run to update to latest sources at any time.

``` make packages ```

Builds all the *.deb packages from the checked out source repos and stages them for further stages. Re-running it will perform an incremental build, only re-building packages which have changed sources in source/<packagename>.

``` make update ```

Builds the stand-alone update file, used for online/offline updating or building ISO images.

``` make iso ```

Builds the ISO image for fresh installation.


``` make clean ```

Cleans up all the temporary files and returns to original state.


## Overrides

It is possible using make and environment variables to override which source repos get checked out during "make checkout" phase.

TRUENAS_BRANCH_OVERRIDE - Can be used to override all source repos at once

<NAME>_OVERRIDE - Can override specific repos, I.E. debootstrap_OVERRIDE="master"
