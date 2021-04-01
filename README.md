# truenas-build

A build framework for TrueNAS SCALE. Want to contribute or collaborate? Join our [Slack instance](https://www.ixsystems.com/community/threads/collaborator-community-slack-instance.85717/ "Slack Instance"). 

Found an issue in the build for SCALE? Please report it on our [Jira bugtracker](https://jira.ixsystems.com).

## Requirements

 - Debian 10 or later (VM or Bare-Metal)
 - 16GB of RAM
 - At least 15GB of free disk space

In addition to the host, you will want to pre-install the following packages:

* build-essential
* debootstrap
* git
* squashfs-tools
* unzip

``` % sudo apt install build-essential debootstrap git squashfs-tools unzip xorriso```

## Usage

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
