"""
This is the place where we try and discover information buried in images.
"""

from __future__ import division

import sys
import os
import tempfile
import math
import atexit
try:
    import cStringIO as StringIO
except ImportError:
    import StringIO

try:
    from PIL import Image, ImageSequence
except ImportError:
    Image = None

from spambayes.safepickle import pickle_read, pickle_write
from spambayes.port import md5

# The email mime object carrying the image data can have a special attribute
# which indicates that a message had an image, but it was large (ie, larger
# than the 'max_image_size' option.)  This allows the provider of the email
# object to avoid loading huge images into memory just to have this image
# stripper ignore it.
# If the attribute exists, it should be the size of the image (we assert it
# is > max_image_size).  The image payload is ignored.
# A 'cleaner' option would be to look at a header - but an attribute was
# chosen to avoid spammers getting wise and 'injecting' the header into the
# message body of a mime section.
image_large_size_attribute = "spambayes_image_large_size"

from spambayes.Options import options

# copied from tokenizer.py - maybe we should split it into pieces...
def log2(n, log=math.log, c=math.log(2)):
    return log(n)/c

def is_executable(prog):
    if sys.platform == "win32":
        return True
    info = os.stat(prog)
    return (info.st_uid == os.getuid() and (info.st_mode & 0100) or
            info.st_gid == os.getgid() and (info.st_mode & 0010) or
            info.st_mode & 0001)

def find_program(prog):
    path = os.environ.get("PATH", "").split(os.pathsep)
    if sys.platform == "win32":
        prog = "%s.exe" % prog
        if hasattr(sys, "frozen"): # a binary (py2exe) build..
            # Outlook plugin puts executables in (for example):
            #    C:/Program Files/SpamBayes/bin
            # so add that directory to the path and make sure we
            # look for a file ending in ".exe".
            if sys.frozen == "dll":
                import win32api
                sentinal = win32api.GetModuleFileName(sys.frozendllhandle)
            else:
                sentinal = sys.executable
            # os.popen() trying to quote both the program and argv[1] fails.
            # So just use the short version.
            # For the sake of safety, in a binary build we *only* look in
            # our bin dir.
            path = [win32api.GetShortPathName(os.path.dirname(sentinal))]
        else:
            # a source build - for testing, allow it in SB package dir.
            import spambayes
            path.insert(0, os.path.abspath(spambayes.__path__[0]))

    for directory in path:
        program = os.path.join(directory, prog)
        if os.path.exists(program) and is_executable(program):
            return program
    return ""

def imconcatlr(left, right):
    """Concatenate two images left to right."""
    w1, h1 = left.size
    w2, h2 = right.size
    result = Image.new("RGB", (w1 + w2, max(h1, h2)))
    result.paste(left, (0, 0))
    result.paste(right, (w1, 0))
    return result

def imconcattb(upper, lower):
    """Concatenate two images top to bottom."""
    w1, h1 = upper.size
    w2, h2 = lower.size
    result = Image.new("RGB", (max(w1, w2), h1 + h2))
    result.paste(upper, (0, 0))
    result.paste(lower, (0, h1))
    return result

def PIL_decode_parts(parts):
    """Decode and assemble a bunch of images using PIL."""
    tokens = set()
    rows = []
    max_image_size = options["Tokenizer", "max_image_size"]
    for part in parts:
        # See 'image_large_size_attribute' above - the provider may have seen
        # an image, but optimized the fact we don't bother processing large
        # images.
        nbytes = getattr(part, image_large_size_attribute, None)
        if nbytes is None: # no optimization - process normally...
            try:
                bytes = part.get_payload(decode=True)
                nbytes = len(bytes)
            except:
                tokens.add("invalid-image:%s" % part.get_content_type())
                continue
        else:
            # optimization should not have remove images smaller than our max
            assert nbytes > max_image_size, (len(bytes), max_image_size)

        if nbytes > max_image_size:
            tokens.add("image:big")
            continue                # assume it's just a picture for now

        # We're dealing with spammers and virus writers here.  Who knows
        # what garbage they will call a GIF image to entice you to open
        # it?
        try:
            image = Image.open(StringIO.StringIO(bytes))
            image.load()
        except:
            # Any error whatsoever is reason for not looking further at
            # the image.
            tokens.add("invalid-image:%s" % part.get_content_type())
            continue
        else:
            # Spammers are now using GIF image sequences.  From examining a
            # miniscule set of multi-frame GIFs it appears the frame with
            # the fewest number of background pixels is the one with the
            # text content.

            if "duration" in image.info:
                # Big assumption?  I don't know.  If the image's info dict
                # has a duration key assume it's a multi-frame image.  This
                # should save some needless construction of pixel
                # histograms for single-frame images.
                bgpix = 1e17           # ridiculously large number of pixels
                try:
                    for frame in ImageSequence.Iterator(image):
                        # Assume the pixel with the largest value is the
                        # background.
                        bg = max(frame.histogram())
                        if bg < bgpix:
                            image = frame
                            bgpix = bg
                # I've empirically determined:
                #   * ValueError => GIF image isn't multi-frame.
                #   * IOError => Decoding error
                except IOError:
                    tokens.add("invalid-image:%s" % part.get_content_type())
                    continue
                except ValueError:
                    pass
            image = image.convert("RGB")

        if not rows:
            # first image
            rows.append(image)
        elif image.size[1] != rows[-1].size[1]:
            # new image, different height => start new row
            rows.append(image)
        else:
            # new image, same height => extend current row
            rows[-1] = imconcatlr(rows[-1], image)

    if not rows:
        return [], tokens

    # now concatenate the resulting row images top-to-bottom
    full_image, rows = rows[0], rows[1:]
    for image in rows:
        full_image = imconcattb(full_image, image)

    fd, pnmfile = tempfile.mkstemp('-spambayes-image')
    os.close(fd)
    full_image.save(open(pnmfile, "wb"), "PPM")

    return [pnmfile], tokens

class OCREngine(object):
    """Base class for an OCR "engine" that extracts text.  Ideally would
       also deal with image format (as different engines will have different
       requirements), but all currently supported ones deal with the PNM
       formats (ppm/pgm/pbm)
    """
    engine_name = None # sub-classes should override.
    def __init__(self):
        pass

    def is_enabled(self):
        """Return true if this engine is able to be used.  Note that
           returning true only means it is *capable* of being used - not that
           it is enabled.  eg, it should check the program is needs to use
           is installed, etc.
        """
        raise NotImplementedError

    def extract_text(self, pnmfiles):
        """Extract the text as an unprocessed stream (but as a string).
           Typically this will be the raw output from the OCR engine.
        """
        raise NotImplementedError

class OCRExecutableEngine(OCREngine):
    """Uses a simple executable that writes to stdout to extract the text"""
    engine_name = None
    def __init__(self):
        # we go looking for the program first use and cache its location
        self._program = None
        OCREngine.__init__(self)

    def is_enabled(self):
        return self.program is not None

    def get_program(self):
        # by default, executable is same as engine name
        if not self._program:
            self._program = find_program(self.engine_name)
        return self._program
    
    program = property(get_program)

    def get_command_line(self, pnmfile):
        raise NotImplementedError, "base classes must override"

    def extract_text(self, pnmfile):
        # Generically reads output from stdout.
        assert self.is_enabled(), "I'm not working!"
        cmdline = self.get_command_line(pnmfile)
        ocr = os.popen(cmdline)
        ret = ocr.read()
        exit_code = ocr.close()
        if exit_code:
            raise SystemError, ("%s failed with exit code %s" %
                                (self.engine_name, exit_code))
        return ret

class OCREngineOCRAD(OCRExecutableEngine):
    engine_name = "ocrad"

    def get_command_line(self, pnmfile):
        scale = options["Tokenizer", "ocrad_scale"] or 1
        charset = options["Tokenizer", "ocrad_charset"]
        return '%s -s %s -c %s -f "%s" 2>%s' % \
                (self.program, scale, charset, pnmfile, os.path.devnull)

class OCREngineGOCR(OCRExecutableEngine):
    engine_name = "gocr"

    def get_command_line(self, pnmfile):
        return '%s "%s" 2>%s' % (self.program, pnmfile, os.path.devnull)

# This lists all engines, with the first listed that is enabled winning.
# Matched with the engine name, as specified in Options.py, via the
# 'engine_name' attribute on the class.
_ocr_engines = [
    OCREngineGOCR,
    OCREngineOCRAD,
]

def get_engine(engine_name):
    if not engine_name:
        candidates = _ocr_engines
    else:
        for e in _ocr_engines:
            if e.engine_name == engine_name:
                candidates = [e]
                break
        else:
            candidates = []
    for candidate in candidates:
        engine = candidate()
        if engine.is_enabled():
            return engine
    return None

class ImageStripper:
    def __init__(self, cachefile=""):
        self.cachefile = os.path.expanduser(cachefile)
        if os.path.exists(self.cachefile):
            self.cache = pickle_read(self.cachefile)
        else:
            self.cache = {}
        self.misses = self.hits = 0
        if self.cachefile:
            atexit.register(self.close)
        self.engine = None
    
    def extract_ocr_info(self, pnmfiles):
        assert self.engine, "must have an engine!"
        textbits = []
        tokens = set()
        for pnmfile in pnmfiles:
            preserve = False
            fhash = md5(open(pnmfile).read()).hexdigest()
            if fhash in self.cache:
                self.hits += 1
                ctext, ctokens = self.cache[fhash]
            else:
                self.misses += 1
                if self.engine.program:
                    try:
                        ctext = self.engine.extract_text(pnmfile).lower()
                    except SystemError, msg:
                        print >> sys.stderr, msg
                        preserve = True
                        ctext = ""
                else:
                    # We should not get here if no OCR is enabled.  If it
                    # is enabled and we have no program, its OK to spew lots
                    # of warnings - they should either disable OCR (it is by
                    # default), or fix their config.
                    print >> sys.stderr, \
                          "No OCR program '%s' available - can't get text!" \
                          % (self.engine.engine_name,)
                    ctext = ""
                ctokens = set()
                if not ctext.strip():
                    # Lots of spam now contains images in which it is
                    # difficult or impossible (using ocrad) to find any
                    # text.  Make a note of that.
                    ctokens.add("image-text:no text found")
                else:
                    nlines = len(ctext.strip().split("\n"))
                    if nlines:
                        ctokens.add("image-text-lines:%d" % int(log2(nlines)))
                self.cache[fhash] = (ctext, ctokens)
            textbits.append(ctext)
            tokens |= ctokens
            if not preserve:
                os.unlink(pnmfile)

        return "\n".join(textbits), tokens

    def analyze(self, engine_name, parts):
        # check engine hasn't changed...
        if self.engine is not None and self.engine.engine_name != engine_name:
            self.engine = None
        # check engine exists and is valid
        if self.engine is None:
            self.engine = get_engine(engine_name)
        if self.engine is None:
            # We only get here if explicitly enabled - spewing msgs is ok.
            print >> sys.stderr, "invalid engine name '%s' - OCR disabled" \
                                 % (engine_name,)
            return "", set()

        if not parts:
            return "", set()

        if Image is not None:
            pnmfiles, tokens = PIL_decode_parts(parts)
        else:
            return "", set()

        if pnmfiles:
            text, new_tokens = self.extract_ocr_info(pnmfiles)
            return text, tokens | new_tokens

        return "", tokens


    def close(self):
        if options["globals", "verbose"]:
            print >> sys.stderr, "saving", len(self.cache),
            print >> sys.stderr, "items to", self.cachefile,
            if self.hits + self.misses:
                print >> sys.stderr, "%.2f%% hit rate" % \
                      (100 * self.hits / (self.hits + self.misses)),
            print >> sys.stderr
        pickle_write(self.cachefile, self.cache)

_cachefile = options["Tokenizer", "crack_image_cache"]
crack_images = ImageStripper(_cachefile).analyze
