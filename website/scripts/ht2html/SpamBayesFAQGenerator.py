#! /usr/bin/env python
"""Minor tweak for faq"""

from SpamBayesGenerator import SpamBayesGenerator
class SpamBayesFAQGenerator(SpamBayesGenerator):
    def get_charset(self):
        return 'utf-8'
