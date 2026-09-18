import io
p='src/dsh/2026-09-18_18_consistency_check_v2.py'
lines=io.open(p,encoding='utf-8').read().split(chr(10))
done=False
for i,l in enumerate(lines):
    if l.strip().startswith('p=p.strip('):
        lines[i]="            STRIP=' '+chr(96)+chr(34)+chr(39)+'\uff0c\u3002\uff09\u3001\u002c\u002e\uff1b:;'"
        lines.insert(i+1,"            p=p.strip(STRIP)")
        done=True; print('已替换第',i+1,'行'); break
if not done: print('未找到目标行')
io.open(p,'w',encoding='utf-8').write(chr(10).join(lines))
