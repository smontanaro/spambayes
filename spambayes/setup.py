from distutils.core import setup

setup(
  name='spambayes',
  scripts=['unheader.py',
           'hammie.py',
           'hammiesrv.py',
           'loosecksum.py',
           'timtest.py',
           'timcv.py',
           'splitndirs.py',
           'runtest.sh',
           'rebal.py',
           'HistToGNU.py',
           'mboxcount.py',
           'mboxtest.py',
           'neiltrain.py',
           'cmp.py',
           'rates.py'],
  py_modules=['classifier',
              'tokenizer',
              'hammie',
              'msgs',
              'Options',
              'Tester',
              'TestDriver',
              'mboxutils']
  )
