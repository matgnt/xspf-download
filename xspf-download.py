#!/usr/bin/python 
#
#
#   Copyright (c) 2004 Robert Kaye
#   Copyright (c) 2010 Matthias Guenther
#       All rights reserved.
#
# Redistribution and use in source and binary forms, with or without 
# modification, are permitted provided that the following conditions 
# are met:
#
#   * Redistributions of source code must retain the above copyright 
#     notice, this list of conditions and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright 
#     notice, this list of conditions and the following disclaimer in 
#     the documentation and/or other materials provided with the distribution.
#   * Neither the name of MusicBrainz nor the names of its contributors 
#     may be used to endorse or promote products derived from this software 
#     without specific prior written permission.
#
#   THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS 
#   "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT 
#   LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS 
#   FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT 
#   OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, 
#   SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED 
#   TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR 
#   PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF 
#   LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING 
#   NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS 
#   SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import sys, urllib2, os, getopt, copy, re
from xml.sax import make_parser, handler, SAXParseException
from time import time as now
from optparse import OptionParser

bufSize = 4096
numTimesInWindow = 32

class PlaylistParser(object):
    
    def __init__(self):
        self.urls = []
        self.title = ""

    def addURL(self, URL):
        self.urls.append(URL)

    def getURLList(self):
        return self.urls

    def getTitle(self):
        return self.title

    def parseFile(self, fileName):
        raise NotImplementedException

# Ha! As if this could be called a parser!
class M3UParser(PlaylistParser): 

    def __init__(self):
        PlaylistParser.__init__(self)

    def parseFile(self, fileName):
       
        file = None
        try:
            file = open(fileName, "r")
            while 1:
               line = file.readline()
               if line:
                   line = line.strip()
                   if line:
                       self.addURL(line.strip())
               else:
                   break
        except:
            pass

        if file:
            file.close()

        return True
                
class XSPFParser(PlaylistParser, handler.ContentHandler):

    def __init__(self):
        PlaylistParser.__init__(self)
        self.path = ""
        self.curURL = ""

    def parseFile(self, fileName):
       
        try:
            parser = make_parser()
            parser.setContentHandler(self)
            parser.parse(fileName)
            return True
        except SAXParseException:
            return False

    def startElement(self, name, attrs):
        self.path += "/%s" % name
        self.content = ""

    def characters(self, content):
        self.content = self.content + content

    def endElement(self, name):

        if self.path == "/playlist/trackList/track/location":
            self.addURL(self.content)

        if self.path == "/playlist/title":
            self.title = self.content

        offset = self.path.rfind("/")
        if offset >= 0:
            self.path = self.path[0:offset]

class Downloader(object):

    def __init__(self):
        self.currentFile = ""
        self.regexp = re.compile(r'[^A-Za-z0-9-_()!,;. ]')

    def getCurrentFile(self):
        return self.currentFile

    def makeFileSystemSafe(self, path):
        return self.regexp.sub('', path)

    def getNameFromFile(self, file):    
        title = os.path.basename(file)
        ext = title.rfind(".")
        if ext >= 0:
            title = title[0:ext]

        return title

    def getFileFromURL(self, url):    
        url = urllib2.unquote(url)
        name = url.rfind("/")
        if name >= 0:
            url = url[name+1:]

        return url

    def download(self):
        parser = None
        url = None
        opts = None
        args = None

        optionparser = OptionParser()
        optionparser.add_option("-x", "--xspf-playlist", help="XSPF playlist URL.", dest="xspf_url")
        optionparser.add_option("-m", "--m3u-playlist", help="M3U playlist URL.", dest="m3u_url")
        optionparser.add_option("-s", "--file-name-substring", help="Must-Have-Substring to choose the track to download.", dest="file_name_substr")
        (opts, args) = optionparser.parse_args();

        if opts.xspf_url:
            url = opts.xspf_url
            parser = XSPFParser()
        elif opts.m3u_url:
            url = opts.m3u_url
            parser = M3UParser()
        else:
            optionparser.print_help()
            sys.exit(-1)

        if not parser.parseFile(url):
            print "Parsing the playlist failed."
            return False

        title = parser.getTitle()
        if not title:
            title = self.getNameFromFile(url)

        # This neeeds to be made filesystem safe
        dir = self.makeFileSystemSafe(title)
        if not os.path.exists(dir):
            try:
               os.mkdir(dir)
            except IOError:
               print "Cannot create directory '%s'" % dir
               return False

        urls = parser.getURLList()

        print "%d urls in %s" % (len(urls), title)
        for url in urls:
            fileName = os.path.join(dir, self.makeFileSystemSafe(self.getFileFromURL(url)))

            if opts.file_name_substr:
                if not opts.file_name_substr in fileName:
                        print "File %s doesn't match your file name substring %s." % (fileName, opts.file_name_substr)
                        continue

            if os.path.exists(fileName):
                print "File %s already exists." % fileName
                continue
            self.currentFile = copy.copy(fileName)
            print "%s -> %s" % (url, fileName)

            req = urllib2.Request(url)
            url_handle = None
            try:
               url_handle = urllib2.urlopen(req)
            except ValueError:
               print "  Don't know how to handle %s" % url
               print 
               continue

            headers = url_handle.info()
            contentLength = int(headers.getheader("Content-Length"))
            if contentLength == 0:
               print "  Download size not known."
           
            try:
               file = open(fileName, "w");
            except IOError:
               print "Cannot create output file '%s'" % fileName
               return True;

            packetTimes = []
            total = 0
            packetCount = 0
            while 1:
                start = now()
                data = url_handle.read(bufSize)
                end = now()
                numRead = len(data)
                if numRead <= 0:
                    break

                if len(packetTimes) >= numTimesInWindow:
                   packetTimes.pop(0)
                packetTimes.append(end - start)
            
                try:
                    file.write(data)
                except IOError:
                    print "Cannot write to disk. Disk full?"
                    break
            
                total += len(data)
                if contentLength > 0 and (packetCount % 16) == 0:
                    if len(packetTimes) == numTimesInWindow:
                        totalTime = 0
                        for t in packetTimes:
                           totalTime += t
                        print "  %d%% complete (%.1f Kb/s)    \r" % ((int(total * 100 / contentLength)), 
                                                         (numTimesInWindow * bufSize) / (totalTime * 1024)),
                    else:
                        print "  %d%% complete\r" % (int(total * 100 / contentLength)),
                    sys.stdout.flush()

                packetCount += 1
            
            url_handle.close()
            file.close()
           
            if total < contentLength:
                print "Incomplete download -- removing file."
                os.unlink(fileName);
            else:
                print "  100% complete                "
            self.currentFile = ""
            print

        print
        print "Download complete."

######
# main
######
if __name__ == "__main__":
    downloader = Downloader()
    try:
        if downloader.download():
            sys.exit(0);
        sys.exit(-1);
    
    except KeyboardInterrupt:
        print "\nInterrupted.",
        try:
            os.unlink(downloader.getCurrentFile())
            print " Removed", downloader.getCurrentFile()
        except:
            print
        sys.exit(-1)
