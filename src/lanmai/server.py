# -*- coding: utf-8 -*-
"""lanmai.server —— 本地 Web 服务（方案 A：浏览器上传 CSV → 体检/标定/报告；澜脉，DSH，2026-09-22）

设计约束：
 ① **只用 Python 标准库**（http.server），不引入任何新依赖；页面不用 JS，纯表单提交（和其他页面一致）；
 ② 默认只监听 127.0.0.1（本机），数据不出本机；要局域网访问须显式 --host 0.0.0.0（会打印提醒）；
 ③ 只调用 core / pipeline / report 的同一套函数，不引入第二套算法；
 ④ 产物落在 --out-dir（默认 ./lanmai_out/<时间戳>/），页面上直接给下载/打开链接；
 ⑤ 上传大小上限 300MB，只接受 .csv/.csv.gz/.gz/.txt/.json，文件名只取 basename（防目录穿越）。

用法：
  python -m lanmai serve [--host 127.0.0.1] [--port 8765] [--out-dir lanmai_out] [--demo-dir results/2026-09-21/lanmai_demo] [--open]
"""
import os, io, re, json, time, argparse, webbrowser
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse, quote

MAX_UPLOAD = 300 * 1024 * 1024
ALLOW_EXT = ('.csv', '.gz', '.txt', '.json')
DEMO_FILES = {'bsm1': ('bsm1_120d_degraded_ts.csv', 'bsm1_baseline.json', 'BSM1 仿真退化轨迹（相对时间；6 个告警）'),
              'metropt3': ('metropt3_prepared.csv.gz', 'metropt3_baseline.json', 'MetroPT-3 真实空压机 214 天（105 个告警）')}
CSS = ('body{margin:0;background:#f6f8fa;color:#1b2733;font-family:Microsoft YaHei,Arial,sans-serif;font-size:14px;line-height:1.7}'
       '.wrap{max-width:940px;margin:0 auto;padding:22px 18px 50px}'
       'h1{font-size:21px;margin:0 0 4px}h2{font-size:16px;margin:22px 0 6px;padding-left:9px;border-left:4px solid #12507b}'
       '.sub{color:#5b6b7c;font-size:12px;margin-bottom:12px}'
       '.card{background:#fff;border:1px solid #e3e8ee;border-radius:8px;padding:12px 14px;margin:10px 0}'
       'label{display:block;font-size:12.5px;color:#41505f;margin:8px 0 3px}'
       'input[type=text],input[type=file],input[type=number],select{width:100%;box-sizing:border-box;padding:6px 8px;border:1px solid #d3dbe4;border-radius:6px;font-size:13px;background:#fff}'
       'button{margin-top:12px;background:#12507b;color:#fff;border:0;border-radius:6px;padding:9px 16px;font-size:14px;cursor:pointer}'
       'button.ghost{background:#eef7ff;color:#12507b;border:1px solid #b6dcfb}'
       '.row{display:flex;gap:12px;flex-wrap:wrap}.row>div{flex:1;min-width:180px}'
       '.warn{background:#fff7e6;border:1px solid #ffd591;border-radius:6px;padding:9px 12px;margin:10px 0;font-size:13px}'
       '.ok{background:#eaf7ee;border:1px solid #b7e3c4;border-radius:6px;padding:9px 12px;margin:10px 0;font-size:13px}'
       'table{width:100%;border-collapse:collapse;background:#fff;font-size:12.5px}'
       'th,td{border:1px solid #e3e8ee;padding:5px 7px;text-align:left}th{background:#f0f6fb}'
       'a{color:#12507b}code{background:#eef2f6;padding:1px 5px;border-radius:4px;font-size:12px}')


def _parse_multipart(body, boundary):
    delim = b'--' + boundary
    fields, files = {}, {}
    for part in body.split(delim):
        if not part or part in (b'--\r\n', b'--', b'\r\n'):
            continue
        if part.startswith(b'\r\n'):
            part = part[2:]
        if part.endswith(b'\r\n'):
            part = part[:-2]
        if b'\r\n\r\n' not in part:
            continue
        head, data = part.split(b'\r\n\r\n', 1)
        txt = head.decode('utf-8', 'replace')
        m = re.search('name="([^"]*)"', txt)
        if not m:
            continue
        name = m.group(1)
        fn = re.search('filename="([^"]*)"', txt)
        if fn and fn.group(1):
            files[name] = (os.path.basename(fn.group(1)), data)
        else:
            fields[name] = data.decode('utf-8', 'replace')
    return fields, files


def _page(msg='', msgkind='ok', out_dir='.', demo_dir=None, files_list=()):
    B = []
    a = B.append
    a('<!DOCTYPE html><html lang=zh-CN><head><meta charset=utf-8>')
    a('<meta name=viewport content="width=device-width,initial-scale=1">')
    a('<title>澜脉 · 本地工作台</title><style>%s</style></head><body><div class=wrap>' % CSS)
    a('<h1>澜脉 · 本地工作台（lanmai serve）</h1>')
    a('<div class=sub>浏览器上传现场数据 → 数据体检 / 基线标定 / 出企业版报告。全部在本机完成，<b>数据不出本机</b>。</div>')
    if msg:
        a('<div class="%s">%s</div>' % ('ok' if msgkind == 'ok' else 'warn', msg))
    a('<h2>① 先标定基线（用一段「健康期」数据）</h2>')
    a('<form class=card method=post action="/calibrate" enctype="multipart/form-data">')
    a('<div class=row><div><label>健康期数据文件（.csv / .csv.gz）</label><input type=file name=health required></div>')
    a('<div><label>通道白名单（可空；逗号分隔）</label><input type=text name=channels placeholder="TP2,TP3,H1,Oil_temperature"></div></div>')
    a('<div class=row><div><label>工况分层</label><select name=state>'
      '<option value=hour>hour（按一天中的时段）</option><option value=col selected>col（按状态列）</option>'
      '<option value=none>none（不分层）</option><option value=quantile>quantile（按负荷分位）</option></select></div>')
    a('<div><label>状态列名（state=col 时必填）</label><input type=text name=state_col placeholder="state"></div>')
    a('<div><label>参考段（单段：0,0.3）</label><input type=text name=ref value="0,0.3"></div></div>')
    a('<div class=row><div><label>多段健康期（可空，推荐：0,0.08;0.09,0.17;0.26,0.34）</label><input type=text name=ref_segments></div>')
    a('<div><label>多段阈值策略</label><select name=thr_policy><option value=median>median（折中）</option><option value=upper>upper（保守压误报）</option></select></div>')
    a('<div><label>分位 q</label><input type=number step=0.001 name=q value=0.999></div></div>')
    a('<button type=submit>生成 baseline.json</button></form>')
    a('<h2>② 出企业版报告（待监测数据 + 已标定基线）</h2>')
    a('<form class=card method=post action="/report" enctype="multipart/form-data">')
    a('<div class=row><div><label>待监测数据文件（.csv / .csv.gz）</label><input type=file name=data required></div>')
    a('<div><label>baseline.json</label><input type=file name=baseline></div></div>')
    a('<div class=row><div><label>重采样（可空：15min / 1min）</label><input type=text name=resample></div>')
    a('<div><label>预热期（可空：1D / 6H）</label><input type=text name=warmup></div>')
    a('<div><label>报告标题（可空）</label><input type=text name=title></div>'
      '<div><label>最多列出告警条数</label><input type=number name=max_alarms value=40></div></div>')
    a('<button type=submit>生成 report.html</button></form>')
    if demo_dir and os.path.isdir(demo_dir):
        a('<h2>③ 用仓库自带样例直接试（不需上传）</h2><div class=card>')
        for k, (d, b, desc) in DEMO_FILES.items():
            if os.path.exists(os.path.join(demo_dir, d)) and os.path.exists(os.path.join(demo_dir, b)):
                a('<form method=post action="/report" enctype="multipart/form-data" '
                  'style="display:inline-block;margin-right:10px">'
                  '<input type=hidden name=demo value="%s"><button class=ghost type=submit>%s</button></form>' % (k, desc))
        a('<div class=sub style="margin-top:8px">样例说明：BSM1 是仿真（相对时间，显示为「第 X 天」）；MetroPT-3 是真实空压机（真实日期）。</div></div>')
    a('<h2>④ 本机已生成的产物</h2>')
    if files_list:
        a('<table><tr><th>文件</th><th>大小(KB)</th><th>时间</th></tr>')
        for rel, sz, mt in files_list:
            a('<tr><td><a href="/out/%s">%s</a></td><td>%.1f</td><td>%s</td></tr>' % (quote(rel), rel, sz / 1024.0, mt))
        a('</table>')
    else:
        a('<div class=sub>（还没有产物）</div>')
    a('<h2>⑤ 口径提醒</h2><div class=warn>阈值必须按现场标定（换参考窗可差 2–4 倍）；参考窗是否健康工具判不了，必须人工确认；本工具只做<b>检测与标定</b>，不含诊断与 RUL；成本参数是占位值。</div>')
    a('<div class=sub>命令行等价物：<code>python -m lanmai inspect/calibrate/watch/report …</code>；详见 docs/10 使用手册。</div>')
    a('</div></body></html>')
    return ''.join(B)


class Handler(BaseHTTPRequestHandler):
    out_dir = '.'
    demo_dir = None
    server_version = 'lanmai-serve/1.0'

    def log_message(self, fmt, *args):
        print('[%s] %s' % (time.strftime('%H:%M:%S'), fmt % args))

    def _send(self, code, body, ctype='text/html; charset=utf-8'):
        data = body.encode('utf-8') if isinstance(body, str) else body
        self.send_response(code)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(data)

    def _list_files(self):
        out = []
        for root, dirs, fs in os.walk(self.out_dir):
            if os.path.basename(root) == 'upload':
                continue
            for f in fs:
                p = os.path.join(root, f)
                rel = os.path.relpath(p, self.out_dir).replace(os.sep, '/')
                out.append((rel, os.path.getsize(p), time.strftime('%H:%M:%S', time.localtime(os.path.getmtime(p)))))
        return sorted(out, key=lambda x: x[2], reverse=True)[:40]

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == '/':
            q = parse_qs(u.query)
            msg = q.get('msg', [''])[0]
            kind = q.get('kind', ['ok'])[0]
            return self._send(200, _page(msg=msg, msgkind=kind, out_dir=self.out_dir,
                                         demo_dir=self.demo_dir, files_list=self._list_files()))
        if u.path.startswith('/out/'):
            rel = os.path.normpath(u.path[len('/out/'):]).replace('\\', '/')
            if rel.startswith('..'):
                return self._send(403, 'forbidden')
            p = os.path.join(self.out_dir, rel)
            if not os.path.isfile(p):
                return self._send(404, 'not found')
            ctype = 'text/html; charset=utf-8' if p.endswith('.html') else 'application/octet-stream'
            return self._send(200, io.open(p, 'rb').read(), ctype)
        if u.path == '/favicon.ico':
            return self._send(204, b'')
        return self._send(404, 'not found')

    def _read_body(self):
        n = int(self.headers.get('Content-Length', '0'))
        if n <= 0:
            return b''
        if n > MAX_UPLOAD:
            raise ValueError('上传超过 300MB 上限')
        buf = b''
        left = n
        while left > 0:
            chunk = self.rfile.read(min(1 << 20, left))
            if not chunk:
                break
            buf += chunk
            left -= len(chunk)
        return buf

    def _new_run_dir(self, prefix):
        d = os.path.join(self.out_dir, '%s_%s' % (prefix, time.strftime('%m%d_%H%M%S')))
        os.makedirs(d, exist_ok=True)
        return d

    def _save(self, dest_dir, name, data):
        ext = os.path.splitext(name)[1].lower()
        if name.lower().endswith('.csv.gz'):
            ext = '.csv.gz'
        if ext not in ALLOW_EXT:
            raise ValueError('不接受的文件类型：%s（只允许 %s）' % (ext, '、'.join(ALLOW_EXT)))
        updir = os.path.join(dest_dir, 'upload')
        os.makedirs(updir, exist_ok=True)
        p = os.path.join(updir, os.path.basename(name))
        io.open(p, 'wb').write(data)
        return p

    def _redirect(self, url):
        self.send_response(303)
        self.send_header('Location', url)
        self.end_headers()

    def do_POST(self):
        try:
            ctype = self.headers.get('Content-Type', '')
            body = self._read_body()
            if 'multipart/form-data' in ctype:
                boundary = ctype.split('boundary=')[1].strip().strip('"').encode()
                fields, files = _parse_multipart(body, boundary)
            elif 'application/x-www-form-urlencoded' in ctype or not ctype:
                fields = {k: v[0] for k, v in parse_qs(body.decode('utf-8', 'replace')).items()}
                files = {}
            else:
                raise ValueError('不支持的表单编码 %s（请在页面表单里提交）' % (ctype or '空'))
        except Exception as e:
            return self._send(400, _page(msg='请求解析失败：%s' % e, msgkind='warn', out_dir=self.out_dir,
                                         demo_dir=self.demo_dir, files_list=self._list_files()))
        try:
            if self.path.startswith('/calibrate'):
                return self._do_calibrate(fields, files)
            if self.path.startswith('/report'):
                return self._do_report(fields, files)
            return self._send(404, 'not found')
        except Exception as e:
            return self._send(500, _page(msg='处理失败：%s: %s' % (type(e).__name__, e), msgkind='warn',
                                         out_dir=self.out_dir, demo_dir=self.demo_dir, files_list=self._list_files()))

    def _do_calibrate(self, fields, files):
        from .core import load_table
        from .pipeline import calibrate
        from . import report as RP
        if 'health' not in files:
            raise ValueError('缺少「健康期数据文件」')
        d = self._new_run_dir('calib')
        name, data = files['health']
        hp = self._save(d, name, data)
        df = load_table(hp, None, None, None)
        chans = [c.strip() for c in fields.get('channels', '').split(',') if c.strip()] or \
                [c for c in df.columns if c != fields.get('state_col') and str(df[c].dtype).startswith(('float', 'int'))]
        segs = None
        if fields.get('ref_segments'):
            segs = []
            for part in fields['ref_segments'].split(';'):
                if not part.strip():
                    continue
                x, y = part.split(',')
                segs.append((float(x), float(y)))
        r0, r1 = [float(v) for v in (fields.get('ref') or '0,0.3').split(',')]
        base = calibrate(df, chans, state_kind=fields.get('state', 'none'), state_col=fields.get('state_col') or None,
                         nbin=4, ref_frac=(r0, r1), ref_segments=segs, thr_policy=fields.get('thr_policy', 'median'),
                         q=float(fields.get('q') or 0.999))
        base['meta']['source'] = hp
        bp = os.path.join(d, 'baseline.json')
        io.open(bp, 'w', encoding='utf-8').write(json.dumps(base, ensure_ascii=False, indent=1))
        tr = base['threshold']
        msg = ('标定完成：参考窗 %s → %s（%d 行）；通道 %d 个；判据阈值 <b>%.4f</b>。'
               '产物：<a href="/out/%s">baseline.json</a>（把它用在第②步）。' % (
                   base['meta']['参考窗起点'], base['meta']['参考窗终点'], base['meta']['参考窗行数'],
                   len(base['channels']), tr['value'], quote(os.path.relpath(bp, self.out_dir).replace(os.sep, '/'))))
        if base.get('warnings'):
            msg += '<br><b>警告（必须人工处理）</b>：' + '；'.join(base['warnings'])
        return self._redirect('/?msg=%s&kind=%s' % (quote(msg), 'ok' if not base.get('warnings') else 'warn'))

    def _do_report(self, fields, files):
        from . import report as RP
        d = self._new_run_dir('report')
        warm = fields.get('warmup') or None
        res = fields.get('resample') or None
        title = fields.get('title') or None
        maxa = int(fields.get('max_alarms') or 40)
        demo = fields.get('demo') or ''
        if demo:
            if not (self.demo_dir and demo in DEMO_FILES):
                raise ValueError('未知样例：%s' % demo)
            dn, bn, _ = DEMO_FILES[demo]
            dp = os.path.join(self.demo_dir, dn)
            bp = os.path.join(self.demo_dir, bn)
        else:
            if 'data' not in files:
                raise ValueError('缺少「待监测数据文件」')
            dn, data = files['data']
            dp = self._save(d, dn, data)
            if 'baseline' in files and files['baseline'][1]:
                bn, bdata = files['baseline']
                bp = self._save(d, bn if bn.endswith('.json') else 'baseline.json', bdata)
            else:
                raise ValueError('缺少 baseline.json（请先在第①步生成，或用第③步样例）')
        out = os.path.join(d, 'report.html')
        msg0 = '样例' if demo else '上传数据'
        print('[报告] %s：%s + %s → %s' % (msg0, os.path.basename(dp), os.path.basename(bp), out))
        path, sm = RP.build_report(dp, bp, out, resample=res, warmup=warm, title=title,
                                  max_alarms=maxa, return_summary=True)
        rel = quote(os.path.relpath(path, self.out_dir).replace(os.sep, '/'))
        return self._redirect('/out/%s' % rel)


def serve(host='127.0.0.1', port=8765, out_dir='lanmai_out', demo_dir=None, open_browser=False):
    os.makedirs(out_dir, exist_ok=True)
    Handler.out_dir = out_dir
    Handler.demo_dir = demo_dir
    httpd = ThreadingHTTPServer((host, port), Handler)
    url = 'http://%s:%d/' % (host if host != '0.0.0.0' else '127.0.0.1', port)
    print('=' * 62)
    print('澜脉 · 本地工作台已启动：%s' % url)
    print('本机访问即可；数据不出本机（全部在本机计算与落盘）。')
    if host == '0.0.0.0':
        print('注意：你用了 --host 0.0.0.0 —— 同网段的其他人也能访问，请自行确认网络环境。')
    print('产物目录：%s ｜ 浏览器里按 Ctrl+C 结束服务' % os.path.abspath(out_dir))
    print('=' * 62)
    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n服务已停止')
    finally:
        httpd.server_close()
    return url


def main(argv=None):
    p = argparse.ArgumentParser(prog='lanmai serve', description='澜脉 · 本地工作台（浏览器上传数据 → 体检/标定/报告）')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--out-dir', default='lanmai_out')
    p.add_argument('--demo-dir', default=None, help='样例数据目录（默认 results/2026-09-21/lanmai_demo）')
    p.add_argument('--open', action='store_true', help='启动后自动打开浏览器')
    a = p.parse_args(argv)
    demo = a.demo_dir or os.path.join('results', '2026-09-21', 'lanmai_demo')
    serve(a.host, a.port, a.out_dir, demo if os.path.isdir(demo) else None, a.open)


if __name__ == '__main__':
    main()
