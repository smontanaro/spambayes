
for j in 1 2 3 4 5; do
  python2.2 incremental.py -s $j -r $1 > output/$1$j.out
  python2.2 mkgraph.py < output/$1$j.out > output/$1$j.mtv
  plotmtv -colorps -o output/$1$j.ps -noxplot output/$1$j.mtv
  gs -sDEVICE=png256 -sOutputFile=output/$1$j.png output/$1$j.ps < /dev/null
done
