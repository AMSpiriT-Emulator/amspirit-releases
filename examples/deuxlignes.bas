1 MODE 1: PRINT"Decrunch"
2 DEG:DIM s(360):FOR i=0 to 360:s(i)=SIN(i):NEXT
3 FOR i=0 to 9: READ n(i):o(i)=i+1: INK i,1:NEXT
4 o(3)=2:o(4)=1
5 c=10
6 WHILE 1
7 c=c+1/16
8 b=2-c\10
9 q=(q+8) AND 127
10 t=(t+11) MOD 360
11 g=(g+1) MOD 3
12 if c>18 THEN c=c-18:INK 1,26:INK 2,23:INK 3,10
13 PRINT
14 d=(c+1/2) AND 3
15 p=s((c*b*180)MOD 360)*b*8
16 a=t and 1
17 SOUND g+1,(1+a)*n(((s(q)+2)*c) MOD 5+5*b-5),14-a,10+2*b-g*2
18 MOVE 60*(s(t)+2*s(c*20))+240,20
19 DRAWR q,p,o(d+1)
20 DRAWR 128-q,-p,o(d)
21 WEND
22 DATA 213,179,142,119,95,239,201,159,134,106
