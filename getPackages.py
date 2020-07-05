#!/usr/bin/python3
import sys
import re
import datetime
import os
import subprocess
from pathlib import posixpath as urlpath
import gzip
import threading
import time
import math

REMOTEURL = "http://mirror.centos.org/centos-8/8/AppStream/x86_64/os/"
LOCALURL = ""
VERBOSE = ""
MESSAGEPREFIX = "AppStream"
THREADUSE = 20

def prnt(*args, **kwargs):
    print("[%s %s]" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), MESSAGEPREFIX), *args, **kwargs)

for arg in sys.argv[1:]:
    if re.match(r"^--help$", arg):
        print("Usage:", sys.argv[0], "[Options]","""

Options:
\t--repourl=<URL to source repository, must be HTTP or HTTPS>
\t--basedir=<Path to local repository>
\t--download-threads=<number of threads>
\t--message-prefix=<string>
\t--help
\t--verbose
""")
        exit(0)
    elif re.match(r"^--repourl=(.+)", arg):
        REMOTEURL = re.match(r"^--repourl=(.+)", arg).group(1)
    elif re.match(r"^--basedir=(.*)", arg):
        LOCALURL = re.match(r"^--basedir=(.*)", arg).group(1)
    elif re.match(r"^--verbose$", arg):
        VERBOSE = True
    elif re.match(r"--download-threads=\d+", arg):
        THREADUSE = int(re.match(r"--download-threads=(\d+)", arg).group(1))
    elif re.match(r"--message-prefix=.+", arg):
        MESSAGEPREFIX = re.match(r"--message-prefix=(.+)", arg).group(1)
    else:
        prnt("WARNING: Unknown Option:", arg, file=sys.stderr)
        prnt("WARNING: Ignoring unknown option")

if VERBOSE:
    prnt("Script File Location:", os.path.abspath(__file__))
    prnt("Current Settings:")
    prnt("REMOTEURL =", REMOTEURL)
    prnt("LOCALURL =", LOCALURL)
    prnt("Download threads:", THREADUSE)

try:
    os.stat(os.path.join(LOCALURL, "repodata", "repomd.xml"))
except FileNotFoundError as e:
    prnt("ERROR: repodata Not Found!", file=sys.stderr)
    print(e)
    exit(1)

assert(type(REMOTEURL) == str)  # REMOTEURL must be a str type
assert(type(LOCALURL)  == str)  # LOCALURL must be a str type
assert(REMOTEURL!= "")  # REMOTEURL must not be empty. Use --repourl=<http or https URL> to set this variable.
assert(LOCALURL != "")  # LOCALURL must not be empty. Use --basedir=<Local path> to set this variable.

prnt("Listing packages")
# Reading repomd.xml
repomd_fd = open(os.path.join(LOCALURL, "repodata", "repomd.xml"), mode="r")
repomd_raw = repomd_fd.read()
repomd_fd.close()
repomd_primary = re.search(r"<data type=\"primary\">(.+?(?=<\/data>))<\/data>", repomd_raw, flags=re.S)
if repomd_primary is None:
    prnt("ERROR: missing primary type in repomd.xml")
    exit(1)

# Find primary file in repomd.xml
repomd_primary_fileloc = re.search(r"<location href=\"([^\"]+)\"", repomd_primary.group(1), flags=re.S).group(1)
repomd_primary_fileloc = os.path.join(LOCALURL, repomd_primary_fileloc)
if VERBOSE:
    prnt("primary file path:", repomd_primary_fileloc)
# Check primary file existence
try:
    os.stat(repomd_primary_fileloc)
except FileNotFoundError as e:
    prnt("ERROR: primary file data not found")
    prnt("primary file data location:", repomd_primary_fileloc)
    exit(1)

# Read primary file
if VERBOSE:
    prnt("Reading primary file:", repomd_primary_fileloc)
if re.match(r".+?(?=\.gz)\.gz$", repomd_primary_fileloc) is not None:
    if VERBOSE:
        prnt("gzip compressed primary file detected")
    primary_fd = gzip.open(repomd_primary_fileloc, mode="rt")
else:
    primary_fd = open(repomd_primary_fileloc, mode="r")
primary_raw = primary_fd.read()
primary_fd.close()

# Parsing informations
packages = []
loc_re = re.compile(r"<location href=\"([^\"]+)\"", flags=re.S)
chksum_re = re.compile(r"<checksum type=\"([^\"]*)\"[^\>]*>([^<]*)<\/checksum>")
size_re = re.compile(r"(<size [^>]*>)", flags=re.S)
size_package_re = re.compile(r"package=\"(\d*)\"", flags=re.S)
for package in re.findall(r"<package .+?(?=<\/package>)<\/package>", primary_raw, flags=re.S):
    p = {}
    loc = loc_re.search(package)
    p["location"] = loc.group(1)
    p["checksum"] = {}
    chksum = chksum_re.search(package)
    (p["checksum"]["type"], p["checksum"]["value"]) = chksum.groups()
    size = size_re.search(package).group(1)
    p["size"] = int(size_package_re.search(size).group(1))
    packages.append(p)

# Check package directory existence
try:
    os.stat(os.path.dirname(os.path.join(LOCALURL, packages[0]["location"])))
except FileNotFoundError as e:
    if VERBOSE:
        prnt("Packages directory not found. Creating...")
    os.makedirs(os.path.dirname(os.path.join(LOCALURL, packages[0]["location"])))

prnt("Informations of", len(packages), "packages read")

# Listing files to be downloaded
# Check file existence => Check size => Checksum
def getAliveThreads(threadPool):
    a = 0
    for i in threadPool:
        if i.is_alive():
            a = a + 1
    return a
prnt("Checking existing local files")
dl_packages = []
hash_re = re.compile(r"= *([0-9a-fA-F]*)")
check_lock = threading.Lock()
check_seq = 0
check_thpool = []
class checkThread(threading.Thread):
    def run(self):
        global dl_packages, LOCALURL, packages, hash_re, check_seq
        while True:
            with check_lock:
                if check_seq < len(packages):
                    my_job = check_seq
                    check_seq += 1
                else:
                    return
            try:
                fstat = os.stat(os.path.join(LOCALURL, packages[my_job]["location"]))
            except FileNotFoundError:
                dl_packages.append(my_job)
                continue
            if fstat.st_size != packages[my_job]["size"]:
                dl_packages.append(my_job)
                continue
            hash_p = subprocess.run(["openssl", packages[my_job]["checksum"]["type"],os.path.join(LOCALURL, packages[my_job]["location"])], stdout=subprocess.PIPE)
            if hash_re.search(hash_p.stdout.decode()).group(1) != packages[my_job]["checksum"]["value"]:
                dl_packages.append(my_job)
        
for th in range(len(os.sched_getaffinity(0)) * 2):
    check_thpool.append(checkThread())
    check_thpool[-1].start()

while getAliveThreads(check_thpool):
    sys.stdout.write("Checking: %d/%d\r" % (check_seq, len(packages)))
    time.sleep(1)
print("Checking: %d/%d" % (len(packages), len(packages)))
prnt("Check completed")
prnt(len(dl_packages), "needs to be downloaded")

if len(dl_packages) > 0:
    downloading_size = 0
    for i in dl_packages:
        downloading_size += packages[i]["size"]
    prnt("%s Bytes to be downloaded" % (f"{downloading_size:,}"))

failed_files = []
# Prepare download
class downloadThread(threading.Thread):
    def run(self):
        global packages, LOCALURL, REMOTEURL, failed_files, VERBOSE
        # prnt(" ".join(["wget", "-O", "\""+ os.path.join(LOCALURL, packages[self._args[0]]["location"]) +"\"", urlpath.join(REMOTEURL, packages[self._args[0]]["location"])]))
        # proc = subprocess.Popen(["wget", "-O", "\""+ os.path.join(LOCALURL, packages[self._args[0]]["location"]) +"\"", urlpath.join(REMOTEURL, packages[self._args[0]]["location"])])
        # proc.wait()
        if VERBOSE:
            prnt(" ".join(["wget", "-O", os.path.join(LOCALURL, packages[self._args[0]]["location"]), urlpath.join(REMOTEURL, packages[self._args[0]]["location"])]))
        retcode = subprocess.call([" ".join(["wget", "-O", os.path.join(LOCALURL, packages[self._args[0]]["location"]), urlpath.join(REMOTEURL, packages[self._args[0]]["location"])])], shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=os.environ)
        if retcode:
            prnt("ERROR: Failed to download", urlpath.join(REMOTEURL, packages[self._args[0]]["location"]), file=sys.stderr)
            failed_files.append(urlpath.join(REMOTEURL, packages[self._args[0]]["location"]))

thread_pool = []
i = 0

while i < len(dl_packages):
    # Clear thread pool
    new_pool = []
    for j in range(len(thread_pool)):
        if thread_pool[j].is_alive():
            new_pool.append(thread_pool[j])
    if len(new_pool) != len(thread_pool):
        thread_pool = new_pool
    
    # Check thread limit reached
    if len(thread_pool) < THREADUSE:
        thread_pool.append(downloadThread(args=(dl_packages[i],)))
        thread_pool[-1].start()
        i = i + 1
    else:
        time.sleep(0.25) # retry after 0.5 secs
    
    sys.stdout.write("\x1b[2KDownloaded: " + str(i-THREADUSE) + "/" + str(len(dl_packages)) + "\r")
    
while getAliveThreads(thread_pool):
    sys.stdout.write("\x1b[2KDownloaded: " + str(len(dl_packages) - getAliveThreads(thread_pool)) + "/" + str(len(dl_packages)) + "\r")
    time.sleep(0.25)

sys.stdout.write("\x1b[2KDownloaded: " + str(len(dl_packages)) + "/" + str(len(dl_packages)) + "\r")
print("")
prnt("Download Completed")