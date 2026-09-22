# -*- coding: utf-8 -*-
"""lanmai 本地工作台（方案 A）冒烟测试 —— 供 run_all 与人工复现（DSH，2026-09-22）
启动 lanmai serve → ① 抓首页 ② 样例一键出报告 ③ 上传数据+基线出报告 ④ 上传健康期数据标定 → 校验产物可打开 → 关闭服务。
用法：python src/dsh/2026-09-22_11_lanmai_serve_smoketest.py [--port 8799] [--keep-out]
"""
import os, sys, io, time, json, subprocess, urllib.request, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = os.path.join(ROOT, 'results', '2026-09-21', 'lanmai_demo')
BOUND = '----lanmaiSmokeBoundary'


def mp(files=(), fields=()):
    """手工构造 multipart/form-data body。"""
    b = []
    for k, v in fields:
        b.append(('--%s\r\nContent-Disposition: form-data; name="%s"\r\n\r\n%s\r\n' % (BOUND, k, v)).encode())
    for k, path in files:
        name = os.path.basename(path)
        b.append(('--%s\r\nContent-Disposition: form-data; name="%s"; filename="%s"\r\nContent-Type: application/octet-stream\r\n\r\n' % (BOUND, k, name)).encode())
        b.append(io.open(path, 'rb').read())
        b.append(b'\r\n')
    b.append(('--%s--\r\n' % BOUND).encode())
    return b''.join(b)


def post(url, files=(), fields=()):
    body = mp(files, fields)
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'multipart/form-data; boundary=%s' % BOUND})
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    op = urllib.request.build_opener(NoRedirect)
    try:
        r = op.open(req, timeout=600)
        return r.status, dict(r.headers), r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode('utf-8', 'replace')


def get(url, timeout=600):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8799)
    ap.add_argument('--out', default='lanmai_out_smoketest')
    a = ap.parse_args()
    out = os.path.join(ROOT, a.out)
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, 'src'))
    log = io.open(os.path.join(ROOT, '_serve_smoke.log'), 'w', encoding='utf-8')
    srv = subprocess.Popen([sys.executable, '-m', 'lanmai', 'serve', '--port', str(a.port), '--out-dir', out],
                           cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    base = 'http://127.0.0.1:%d' % a.port
    rows = []
    try:
        ok = False
        for _ in range(40):
            time.sleep(0.5)
            st, _t = get(base + '/', timeout=10)
            if st == 200:
                ok = True
                break
        rows.append(('服务启动', '通过' if ok else '失败', base))
        if not ok:
            raise RuntimeError('服务未在 20 秒内起来')
        st, home = get(base + '/')
        rows.append(('① 首页', '通过' if (st == 200 and '本地工作台' in home) else '失败', 'HTTP %d' % st))
        st, h, _b = post(base + '/report', fields=[('demo', 'bsm1')])
        loc = h.get('Location', '')
        st2, rep = get(base + loc) if loc else (0, '')
        rows.append(('② 样例一键出报告', '通过' if (st == 303 and st2 == 200 and '告警' in rep) else '失败', loc))
        st, h, _b = post(base + '/report',
                         files=[('data', os.path.join(D, 'bsm1_120d_degraded_ts.csv')),
                                ('baseline', os.path.join(D, 'bsm1_baseline.json'))],
                         fields=[('warmup', '1D'), ('title', '冒烟测试报告')])
        loc2 = h.get('Location', '')
        st2, rep2 = get(base + loc2) if loc2 else (0, '')
        rows.append(('③ 上传数据+基线出报告', '通过' if (st == 303 and st2 == 200 and '冒烟测试报告' in rep2) else '失败', loc2))
        st, h, _b = post(base + '/calibrate',
                         files=[('health', os.path.join(D, 'bsm1_120d_baseline_ts.csv'))],
                         fields=[('state', 'hour'), ('ref', '0,0.1'), ('channels', 'SO3,SO4,SO5')])
        rows.append(('④ 上传健康期数据标定', '通过' if st == 303 else '失败', h.get('Location', '')[:60] + '…'))
        st, home2 = get(base + '/')
        rows.append(('⑤ 产物列表（只列产物、不列上传）', '通过' if ('baseline.json' in home2 and 'bsm1_120d_baseline_ts.csv' not in home2) else '失败', ''))
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=15)
        except Exception:
            srv.kill()
        log.close()
    print('lanmai 本地工作台冒烟结果：')
    bad = 0
    for k, v, extra in rows:
        print('  %-28s %-4s %s' % (k, v, extra))
        bad += (v != '通过')
    print('结论：%s（%d/%d 通过）' % ('全部通过' if bad == 0 else '有失败项', len(rows) - bad, len(rows)))
    return 0 if bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
