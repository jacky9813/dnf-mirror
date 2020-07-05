# DNF Repository Mirroring Tool
A tool to replace reposync based on Python 3

## Example
```bash
$./getrepo --localrepo=$(pwd) --remoterepo=http://mirror.centos.org/centos-8/8/AppStream/x86_64/os/ --verbose --reponame=AppStream
```

## System Requirements
* Python 3.6+
* OpenSSL
* wget

## Features
* Multi-threaded file check and multiple download stream.

## Future Plan
* Syncronize multiple repositories in one command
* Read repositories from /etc/yum.repos.d