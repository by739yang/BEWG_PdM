# -*- coding: utf-8 -*-
"""重截说明书里的 6 张界面截图（图 3-14/15/16、3-20/21/22）。

原理：把目标页面用「宽窗口 + 指定设备像素比」整页渲染一次，再从 DOM 里读出章节真实 y 位置，
按目标宽高比精确裁切 —— 不走 PowerShell 文本往返，避免中文变乱码。

用法：
  python src/dsh/2026-09-22_18_shots_recrop.py html    # 生成探针页（Edge dump-dom 用）
  # 然后按 SHOTS 里的 (w, hwin) 逐个 dump-dom 到 tmp/dom_q<i>.txt 并截图到 tmp/hq_<i>.png
  python src/dsh/2026-09-22_18_shots_recrop.py check   # 读探针、算裁切框、打印每张图覆盖的章节
  python src/dsh/2026-09-22_18_shots_recrop.py crop    # 裁切并写入 tmp/fix2/
"""
import io, os, json, re, html, sys
import numpy as np
from PIL import Image

SHOTS = [
    dict(shot='s7_report_metro_kpi.png', page='demo/report_metropt3.html', w=1200, hwin=2550, tw=2400, th=3400, start='一、数据体检'),
    dict(shot='s8_report_metro_alarms.png', page='demo/report_metropt3.html', w=1200, hwin=3800, tw=2400, th=3200, start='三、分级告警'),
    dict(shot='s9_report_metro_tail.png', page='demo/report_metropt3.html', w=1200, hwin=6600, tw=2400, th=3400, start='四、图'),
    dict(shot='s10_demo_detect.png', page='demo/lanmai_demo.html', w=1200, hwin=2400, tw=2400, th=3500, start='一、检测'),
    dict(shot='s11_demo_twin.png', page='demo/lanmai_demo.html', w=1600, hwin=7500, tw=2400, th=3732, start='八、数字孪生闭环'),
    dict(shot='s12_demo_routeb.png', page='demo/lanmai_demo.html', w=2000, hwin=14600, tw=2400, th=4432, start='路线 B：BSM2'),
]
MARGIN = 30
PROBE_JS = """<script>
(function(){
function T(e){ return (e.textContent||'').replace(/\\s+/g,' ').trim().slice(0,36); }
var out=[];
document.querySelectorAll('h1,h2,h3,h4,img,canvas,table').forEach(function(e){
  var r=e.getBoundingClientRect();
  out.push(e.tagName+'|'+Math.round(r.top+window.scrollY)+'|'+Math.round(r.height)+'|'+T(e));
});
var d=document.createElement('div');
d.textContent='@@P@@'+JSON.stringify({docH:document.documentElement.scrollHeight, items:out})+'@@E@@';
document.body.appendChild(d);
})();
</script>"""


def parse_dump(path):
    raw = io.open(path, encoding='utf-8', errors='ignore').read()
    for m in re.finditer(r'@@P@@(.*?)@@E@@', raw, re.S):
        cand = html.unescape(m.group(1)).strip()
        if cand.startswith('{'):
            try:
                return json.loads(cand)
            except Exception:
                pass
    return None


def find(items, prefix):
    for it in items:
        q = it.split('|')
        if len(q) > 3 and q[0] == 'H2' and q[3].startswith(prefix):
            return int(q[1])
    return None


def gen_probe_pages():
    for s in SHOTS:
        t = io.open(s['page'], encoding='utf-8').read()
        dst = os.path.join(os.path.dirname(s['page']), '_pk_%s.html' % os.path.splitext(s['shot'])[0])
        io.open(dst, 'w', encoding='utf-8', newline='').write(t + PROBE_JS)
    print('探针页已生成 %d 个' % len(SHOTS))


def check():
    plan, out = [], []
    for i, s in enumerate(SHOTS):
        d = parse_dump('tmp/dom_q%d.txt' % i)
        if d is None:
            out.append('%s：探针缺失' % s['shot']); continue
        y = find(d['items'], s['start'])
        scale = s['tw'] / s['w']
        bh = int(round(s['w'] * s['th'] / s['tw']))
        y0 = max(0, (y if y is not None else 0) - MARGIN)
        plan.append(dict(s, y=y, y0=y0, bh=bh, scale=scale))
        inside = []
        for it in d['items']:
            q = it.split('|')
            if len(q) >= 4 and q[0] in ('H2', 'IMG') and y0 <= int(q[1]) < y0 + bh:
                inside.append(q[3] if q[3] else 'IMG')
        out.append('%-28s 宽%-5d 标题y=%-6s 裁y0=%-6d 高%-5d 窗口%-6d %s' % (
            s['shot'], s['w'], y, y0, bh, s['hwin'], 'OK' if y0 + bh <= s['hwin'] else '!! 窗口太矮'))
        out.append('      含：' + ' / '.join(inside[:7]))
    io.open('tmp/plan2.json', 'w', encoding='utf-8').write(json.dumps(plan, ensure_ascii=False, indent=1))
    print(chr(10).join(out))


def crop():
    plan = json.load(io.open('tmp/plan2.json', encoding='utf-8'))
    os.makedirs('tmp/fix2', exist_ok=True)
    for i, p in enumerate(plan):
        im = Image.open('tmp/hq_%d.png' % i).convert('RGB')
        box = (0, int(p['y0'] * p['scale']), im.size[0], int((p['y0'] + p['bh']) * p['scale']))
        c = im.crop(box)
        if c.size != (p['tw'], p['th']):
            c = c.resize((p['tw'], p['th']), Image.LANCZOS)
        c.save('tmp/fix2/%s' % p['shot'], optimize=True)
        g = np.asarray(c.convert('L'), dtype=np.float32)
        print('%-28s %s 墨迹 %.2f%%' % (p['shot'], c.size, (g < 200).mean() * 100))


if __name__ == '__main__':
    action = sys.argv[1] if len(sys.argv) > 1 else 'check'
    {'html': gen_probe_pages, 'check': check, 'crop': crop}[action]()