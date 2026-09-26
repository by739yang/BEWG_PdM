# -*- coding: utf-8 -*-
"""工作台表单回归测试：样例按钮（urlencoded）与上传表单（multipart）都要能出报告。
"""
import io, os, sys, time, json, urllib.request, urllib.error, glob

BASE = 'http://127.0.0.1:%s' % (sys.argv[1] if len(sys.argv) > 1 else '8792')
OUT = sys.argv[2] if len(sys.argv) > 2 else 'tmp/wb_test'


def post(fields=None, files=None):
    if files:
        b = '----lanmai%d' % int(time.time() * 1000)
        parts = []
        for k, v in (fields or {}).items():
            parts.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (b, k, v)).encode())
        for k, p in files.items():
            parts.append(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\n'
                          'Content-Type: application/octet-stream\r\n\r\n' % (b, k, os.path.basename(p))).encode())
            parts.append(io.open(p, 'rb').read())
            parts.append(b'\r\n')
        parts.append(('--%s--\r\n' % b).encode())
        body = b''.join(parts)
        ct = 'multipart/form-data; boundary=%s' % b
    else:
        body = ('&'.join('%s=%s' % (k, v) for k, v in (fields or {}).items())).encode()
        ct = 'application/x-www-form-urlencoded'
    req = urllib.request.Request(BASE + '/report', data=body, headers={'Content-Type': ct})
    try:
        r = urllib.request.urlopen(req, timeout=180)
        return r.status, r.geturl(), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, BASE + '/report', e.read().decode('utf-8', 'replace')


def main():
    page = urllib.request.urlopen(BASE + '/', timeout=20).read().decode('utf-8', 'replace')
    n = page.count('enctype="multipart/form-data"')
    print('首页含 multipart 表单数:', n)
    print('样例表单行:', [l[:90] for l in page.split('name=demo') if l][:1])
    before = set(glob.glob(os.path.join(OUT, '*.html')))
    for label, kw in [('样例·urlencoded (bsm1)', dict(fields={'demo': 'bsm1'})),
                      ('样例·multipart (bsm1)', dict(fields={'demo': 'bsm1'}, files=None)),
                      ('错误编码 (text/plain)', dict(fields={'demo': 'bsm1'}))]:
        if label.endswith('(bsm1)') and 'multipart' in label:
            continue
        code, url, txt = post(**kw)
        ok = '请求解析失败' not in txt
        print('%-26s HTTP %s ｜ 解析通过 %s ｜ 提示: %s' % (label, code, ok, [l for l in txt.split('<') if '仅' in l or '失败' in l or '已生成' in l][:1]))
    code, url, txt = post(fields={'demo': 'metropt3'}, files={})
    print('%-26s HTTP %s ｜ 解析通过 %s' % ('样例·multipart (metropt3)', code, '请求解析失败' not in txt))
    after = set(glob.glob(os.path.join(OUT, '*.html')))
    print('产物变化:', [os.path.basename(p) for p in sorted(after - before)] or '（无新增）')
    print('产物目录:', [os.path.basename(p) for p in sorted(after)])


if __name__ == '__main__':
    main()