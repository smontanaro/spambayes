from distutils.core import setup

setup(
  name='spambayes', 
  scripts=['unheader.py', 'hammie.py'],
  py_modules=['classifier', 'tokenizer']
  )

