from distutils.core import setup

setup(
  name='spambayes', 
  scripts=['unheader.py',
           'hammie.py',
           'loosecksum.py',
           'timtest.py',
           'timcv.py',
           'splitndirs.py',
           'runtest.sh',
           'rebal.py',
           'cmp.py',
           'rates.py'],
  py_modules=['classifier',
              'tokenizer',
              'Options',
              'Tester',
              'TestDriver',
              'mboxutils']
  )
