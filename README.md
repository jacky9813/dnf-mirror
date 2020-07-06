# DNF Repository Mirroring Tool
A tool to replace reposync based on Python 3

## Example
```bash
$./getrepo --localrepo=$(pwd) --remoterepo=http://mirror.centos.org/centos-8/8/AppStream/x86_64/os/ --verbose --reponame=AppStream
```

## System Requirements
* Python 3.6+ with SQLite3 support
* OpenSSL
* wget

## Features
* Multi-threaded file check.
* Multiple download stream.

## Future Plan
* Syncronize multiple repositories in one command
* Get repository informations from /etc/yum.repos.d
* Check existing repodata checksum before downloading