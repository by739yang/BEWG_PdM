import io
p='src/dsh/2026-09-18_18_consistency_check_v2.py'; t=io.open(p,encoding='utf-8').read()
old="    STRIP=' '+chr(96)+chr(34)+chr(39)+'，。）)、,。；:;'"
new="    STRIP=' '+chr(96)+chr(34)+chr(39)+chr(46)+'，。）)、,。；:;'"
assert old in t, 'STRIP line not found'
io.open(p,'w',encoding='utf-8').write(t.replace(old,new))
print('STRIP 已加入英文句号')
