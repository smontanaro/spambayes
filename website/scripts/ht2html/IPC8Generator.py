"""Generates the www.python.org website style
"""

from PDOGenerator import PDOGenerator

class IPC8Generator(PDOGenerator):
    AUTHOR = 'python-registrar@foretec.com'

    # python.org color scheme overrides
    def get_lightshade(self):
        return '#99cccc'

    def get_darkshade(self):
        return '#207552'
