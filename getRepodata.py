#!/usr/bin/python3
import urllib.parse
import http.client
from pathlib import posixpath as path
import sys
import re
import os
import gzip
import datetime
import hashlib

BASEURL = "http://mirror.centos.org/centos-8/8/AppStream/x86_64/os/"
LOCALPATH = ""
MESSAGEPREFIX = "AppStream"
VERBOSE = False

def print_err(*args, **kwargs):
    print("[%s %s]: ERROR" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), MESSAGEPREFIX), *args, file=sys.stderr, **kwargs)
def print_log(*args, **kwargs):
    print("[%s %s]:" % (datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"), MESSAGEPREFIX), *args, **kwargs)

def sendHttpRequest(connection, method, path, headers={}, data=""):
    connection.putrequest(method, path)
    for header in headers:
        connection.putheader(header, headers[header])
    connection.endheaders()
    connection.send(data)
    return connection.getresponse()

# Parsing arguments
for arg in sys.argv[1:]:
    if re.match(r"--help", arg):
        print("Usage:", sys.argv[0], "[Options]", """

Options:
\t--repourl=<location of remote repository>\tSpecifies source repository URL (HTTP or HTTPS required)
\t--basedir=<local location for downloading>\tSpecifies desination repository directory (Local path only)
\t--message-prefix=<string>
\t--help                                   \tShow this message
\t--verbose                                \tShow all status output
""")
        exit(0)
    elif re.match(r"--repourl=(.+)", arg):
        BASEURL = re.match(r"--repourl=(.+)", arg).group(1)
    elif re.match(r"--basedir=(.+)", arg):
        LOCALPATH = re.match(r"--basedir=(.+)", arg).group(1)
    elif re.match(r"--message-prefix=.+", arg):
        MESSAGEPREFIX = re.match(r"--message-prefix=(.+)", arg).group(1)
    elif re.match(r"--verbose", arg):
        VERBOSE = True
    else:
        print_err("Unknown argument:", arg)

if VERBOSE:
    print_log("Remote Base URL:", BASEURL)
    print_log("Local Base path:", LOCALPATH)

# Download repodata
base = urllib.parse.urlparse(BASEURL)
print_log("Creating Connection")
if VERBOSE:
    print_log("Scheme: ", base.scheme, ", hostname:", base.netloc)
httpAgent = (http.client.HTTPSConnection if base.scheme == "https" else http.client.HTTPConnection)(base.netloc)

print_log("Sending request for repomd.xml")
if VERBOSE:
    print_log("GET", path.join(base.path, "repodata", "repomd.xml"))
repomd_response = sendHttpRequest(httpAgent, "GET", path.join(base.path, "repodata", "repomd.xml"))

if VERBOSE:
    print_log("Returned HTTP Status:", repomd_response.status)
if repomd_response.status != 200:
    print_err("HTTP Status " + str(repomd_response.status))
    exit(1)

print_log("Parsing repomd.xml")
repomd_rawcontent = repomd_response.read(int(repomd_response.getheader("Content-Length"))).decode()
repomd_content = {}
repomd_regex = {}
repomd_regex["datatype"] = re.compile(r"\<data type\=\"([^\"]*)\"\>")
repomd_regex["checksumtype"] = re.compile(r"\<checksum type\=\"([^\"]*)\"\>")
repomd_regex["checksumvalue"] = re.compile(r"\<checksum[^\>]*\>([^\<]*)\<\/checksum\>")
repomd_regex["locationhref"] = re.compile(r"\<location href\=\"([^\"]*)\"")
repomd_regex["size"] = re.compile(r"\<size\>([^\<]+)\<\/size\>")

for repomd_data in re.findall(r"(\<data[ \>].+?(?=<\/data>)\<\/data\>)", repomd_rawcontent, flags=re.S):
    # print_log(repomd_data)
    data = {}
    data["type"] = repomd_regex["datatype"].search(repomd_data).group(1)
    data["checksum"] = {}
    data["checksum"]["type"] = repomd_regex["checksumtype"].search(repomd_data).group(1)
    data["checksum"]["value"] = repomd_regex["checksumvalue"].search(repomd_data).group(1)
    data["location"] = repomd_regex["locationhref"].search(repomd_data).group(1)
    data["size"] = int(repomd_regex["size"].search(repomd_data).group(1))
    repomd_content[data["type"]] = data

for i in repomd_content:
    print_log("sending request for", repomd_content[i]["type"], "file")
    if VERBOSE:
        print_log("GET", path.join(base.path, repomd_content[i]["location"]))
    resp = sendHttpRequest(httpAgent, "GET", path.join(base.path, repomd_content[i]["location"]))
    if VERBOSE:
        print_log("Returned HTTP Status:", resp.status)
    if resp.status != 200:
        print_err("Failed to get file", path.join(base.path, repomd_content[i]["location"]))
        exit(1)
    if int(resp.getheader("Content-Length")) != repomd_content[i]["size"]:
        print_err("Size mismatch, expected:", repomd_content[i]["size"], ", from HTTP response:", resp.getheader("Content-Length"))
    repomd_content[i]["rawdata"] = resp.read(repomd_content[i]["size"])
    print_log("Checking file integrity")
    h = hashlib.new(repomd_content[i]["checksum"]["type"], data=repomd_content[i]["rawdata"])
    chkvalue = h.hexdigest()
    if VERBOSE:
        print_log("Expected checksum: ", repomd_content[i]["checksum"]["value"])
        print_log(repomd_content[i]["checksum"]["type"], "result:", chkvalue)
    if chkvalue != repomd_content[i]["checksum"]["value"]:
        print_err("CHECKSUM MISMATCH")

try:
    os.stat(os.path.join(LOCALPATH, "repodata"))
except FileNotFoundError as e:
    os.makedirs(os.path.join(LOCALPATH, "repodata"))
print_log("Saving repodata to disk")

if VERBOSE:
    print_log("Opening file:", os.path.join(LOCALPATH, "repodata", "repomd.xml"))
fd = open(os.path.join(LOCALPATH, "repodata", "repomd.xml"), mode="w")
if VERBOSE:
    print_log("Writing file")
fd.write(repomd_rawcontent)
fd.flush()
if VERBOSE:
    print_log("Closing file")
fd.close()
for repodata in repomd_content:
    if VERBOSE:
        print_log("Opening file:", os.path.join(LOCALPATH, repomd_content[repodata]["location"]))
    fd = open(os.path.join(LOCALPATH, repomd_content[repodata]["location"]), mode="wb")
    if VERBOSE:
        print_log("Writing file")
    fd.write(repomd_content[repodata]["rawdata"])
    fd.flush()
    if VERBOSE:
        print_log("Closing file")
    fd.close()

print_log("downloading repomd.xml.asc")
if VERBOSE:
    print_log("GET", path.join(base.path, "repodata/repomd.xml.asc"))
with sendHttpRequest(httpAgent, "GET", path.join(base.path, "repodata/repomd.xml.asc")) as resp:
    if VERBOSE:
        print_log("Returned HTTP Status:", resp.status)
    if resp.status != 200:
        print_err("Failed to get repomd.xml.asc")
        exit(1)
    if VERBOSE:
        print_log("Opening file", os.path.join(LOCALPATH, "repodata/repomd.xml.asc"))
    fd = open(os.path.join(LOCALPATH, "repodata/repomd.xml.asc"), mode="wb")
    if VERBOSE:
        print_log("Writing file")
    fd.write(resp.read(int(resp.getheader("Content-Length"))))
    fd.flush()
    if VERBOSE:
        print_log("Closing file")
    fd.close()

print_log("Done")

