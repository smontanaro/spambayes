"""
This is the place where we try and discover information buried in images.
"""

from __future__ import division

import sys
import os
import tempfile
import math
import time
import md5
import atexit
try:
    import cPickle as pickle
except ImportError:
    import pickle
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    # We have three possibilities for Set:
    #  (a) With Python 2.2 and earlier, we use our compatsets class
    #  (b) With Python 2.3, we use the sets.Set class
    #  (c) With Python 2.4 and later, we use the builtin set class
    Set = set
except NameError:
    try:
        from sets import Set
    except ImportError:
        from spambayes.compatsets import Set

from spambayes.Options import options

# copied from tokenizer.py - maybe we should split it into pieces...
def log2(n, log=math.log, c=math.log(2)):
    return log(n)/c

# I'm sure this is all wrong for Windows.  Someone else can fix it. ;-)
def is_executable(prog):
    info = os.stat(prog)
    return (info.st_uid == os.getuid() and (info.st_mode & 0100) or
            info.st_gid == os.getgid() and (info.st_mode & 0010) or
            info.st_mode & 0001)

def find_program(prog):
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        program = os.path.join(directory, prog)
        if os.path.exists(program) and is_executable(program):
            return program
    return ""

def find_decoders():
    # check for filters to convert to netpbm
    for decode_jpeg in ["jpegtopnm", "djpeg"]:
        if find_program(decode_jpeg):
            break
    else:
        decode_jpeg = None
    for decode_png in ["pngtopnm"]:
        if find_program(decode_png):
            break
    else:
        decode_png = None
    for decode_gif in ["giftopnm"]:
        if find_program(decode_gif):
            break
    else:
        decode_gif = None

    decoders = {
        "image/jpeg": decode_jpeg,
        "image/gif": decode_gif,
        "image/png": decode_png,
        }
    return decoders

def imconcat(im1, im2):
    # concatenate im1 and im2 left-to-right
    w1, h1 = im1.size
    w2, h2 = im2.size
    im3 = Image.new("RGB", (w1+w2, max(h1, h2)))
    im3.paste(im1, (0, 0))
    im3.paste(im2, (0, w1))
    return im3

class ImageStripper:
    def __init__(self, cachefile=""):
        self.cachefile = os.path.expanduser(cachefile)
        if os.path.exists(self.cachefile):
            self.cache = pickle.load(open(self.cachefile))
        else:
            self.cache = {}
        self.misses = self.hits = 0
        if self.cachefile:
            atexit.register(self.close)

    def NetPBM_decode_parts(self, parts, decoders):
        pnmfiles = []
        for part in parts:
            decoder = decoders.get(part.get_content_type())
            if decoder is None:
                continue
            try:
                bytes = part.get_payload(decode=True)
            except:
                continue

            if len(bytes) > options["Tokenizer", "max_image_size"]:
                continue                # assume it's just a picture for now

            fd, imgfile = tempfile.mkstemp()
            os.write(fd, bytes)
            os.close(fd)

            fd, pnmfile = tempfile.mkstemp()
            os.close(fd)
            os.system("%s <%s >%s 2>dev.null" % (decoder, imgfile, pnmfile))
            pnmfiles.append(pnmfile)
            os.unlink(imgfile)

        if not pnmfiles:
            return

        if len(pnmfiles) > 1:
            if find_program("pnmcat"):
                fd, pnmfile = tempfile.mkstemp()
                os.close(fd)
                os.system("pnmcat -lr %s > %s 2>/dev/null" %
                          (" ".join(pnmfiles), pnmfile))
                for f in pnmfiles:
                    os.unlink(f)
                pnmfiles = [pnmfile]

        return pnmfiles

    def PIL_decode_parts(self, parts):
        full_image = None
        for part in parts:
            try:
                bytes = part.get_payload(decode=True)
            except:
                continue

            if len(bytes) > options["Tokenizer", "max_image_size"]:
                continue                # assume it's just a picture for now

            # We're dealing with spammers here - who knows what garbage they
            # will call a GIF image to entice you to open it?
            try:
                image = Image.open(StringIO.StringIO(bytes))
                image.load()
            except IOError:
                continue
            else:
                image = image.convert("RGB")

            if full_image is None:
                full_image = image
            else:
                full_image = imconcat(full_image, image)

        if not full_image:
            return

        fd, pnmfile = tempfile.mkstemp()
        os.close(fd)
        full_image.save(open(pnmfile, "wb"), "PPM")

        return [pnmfile]

    def extract_ocr_info(self, pnmfiles):
        fd, orf = tempfile.mkstemp()
        os.close(fd)

        textbits = []
        tokens = Set()
        for pnmfile in pnmfiles:
            fhash = md5.new(open(pnmfile).read()).hexdigest()
            if fhash in self.cache:
                self.hits += 1
                ctext, ctokens = self.cache[fhash]
            else:
                self.misses += 1
                ocr = os.popen("ocrad -x %s < %s 2>/dev/null" % (orf, pnmfile))
                ctext = ocr.read().lower()
                ocr.close()
                ctokens = set()
                for line in open(orf):
                    if line.startswith("lines"):
                        nlines = int(line.split()[1])
                        if nlines:
                            ctokens.add("image-text-lines:%d" %
                                        int(log2(nlines)))
                self.cache[fhash] = (ctext, ctokens)
            textbits.append(ctext)
            tokens |= ctokens
            os.unlink(pnmfile)
        os.unlink(orf)

        return "\n".join(textbits), tokens

    def analyze(self, parts):
        if not parts:
            return "", Set()

        # need ocrad
        if not find_program("ocrad"):
            return "", Set()

        if Image is not None:
            pnmfiles = self.PIL_decode_parts(parts)
        else:
            pnmfiles = self.NetPBM_decode_parts(parts, find_decoders())

        if pnmfiles:
            return self.extract_ocr_info(pnmfiles)

        return "", Set()


    def close(self):
        if options["globals", "verbose"]:
            print >> sys.stderr, "saving", len(self.cache),
            print >> sys.stderr, "items to", self.cachefile,
            if self.hits + self.misses:
                print >> sys.stderr, "%.2f%% hit rate" % \
                      (100 * self.hits / (self.hits + self.misses)),
            print >> sys.stderr
        pickle.dump(self.cache, open(self.cachefile, "wb"))

_cachefile = options["Tokenizer", "crack_image_cache"]
crack_images = ImageStripper(_cachefile).analyze
