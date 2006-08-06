"""
This is the place where we try and discover information buried in images.
"""

import os
import tempfile
import math
import time

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

def decode_parts(parts, decoders):
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

def extract_ocr_info(pnmfiles):
    fd, orf = tempfile.mkstemp()
    os.close(fd)

    textbits = []
    tokens = Set()
    for pnmfile in pnmfiles:
        ocr = os.popen("ocrad -x %s < %s 2>/dev/null" % (orf, pnmfile))
        textbits.append(ocr.read())
        ocr.close()
        for line in open(orf):
            if line.startswith("lines"):
                nlines = int(line.split()[1])
                if nlines:
                    tokens.add("image-text-lines:%d" % int(log2(nlines)))

        os.unlink(pnmfile)
    os.unlink(orf)

    return "\n".join(textbits), tokens

class ImageStripper:
    def analyze(self, parts):
        if not parts:
            return "", Set()

        # need ocrad
        if not find_program("ocrad"):
            return "", Set()

        decoders = find_decoders()
        pnmfiles = decode_parts(parts, decoders)

        if not pnmfiles:
            return "", Set()

        return extract_ocr_info(pnmfiles)

        
