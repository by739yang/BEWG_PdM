# -*- coding: utf-8 -*-
"""只替换 docx 里的图片字节（不动正文/排版），生成一份高清图副本。
原图与 docx 内嵌图片字节一致 → 用 md5 精确配对后替换为 2x 像素的新截图。
用法：python src/dsh/2026-09-22_17_sharpen_docx_images.py
"""
import io, os, zipfile, hashlib, sys
from PIL import Image

SRC = 'deliverables/澜脉_项目说明书.docx'
DST = 'deliverables/澜脉_项目说明书_高清图.docx'
NEW = {
    's1_landing.png': 'tmp/new/s1_landing.png',
    's2_demo_dashboard.png': 'tmp/new/s2_demo_dashboard.png',
    's3_twin.png': 'tmp/new/s3_twin.png',
    's4_report_metropt3.png': 'tmp/new/s4_report_metropt3.png',
    's5_report_bsm1.png': 'tmp/new/s5_report_bsm1.png',
    's6_workbench.png': 'tmp/new2/s6_workbench.png',
    's7_report_metro_kpi.png': 'tmp/new/s7_report_metro_kpi.png',
    's8_report_metro_alarms.png': 'tmp/new/s8_report_metro_alarms.png',
    's9_report_metro_tail.png': 'tmp/new/s9_report_metro_tail.png',
    's10_demo_detect.png': 'tmp/new/s10_demo_detect.png',
    's11_demo_twin.png': 'tmp/new/s11_demo_twin.png',
    's12_demo_routeb.png': 'tmp/new/s12_demo_routeb.png',
    's13_twin_anim.png': 'tmp/new2/s13_twin_anim.png',
}


def md5(b):
    return hashlib.md5(b).hexdigest()


def main():
    shot_md5 = {}
    for name in NEW:
        p = 'deliverables/shots/' + name
        shot_md5[md5(io.open(p, 'rb').read())] = name
    zin = zipfile.ZipFile(SRC)
    items = zin.infolist()
    replaced, untouched, unmatched = [], 0, []
    zout = zipfile.ZipFile(DST, 'w', zipfile.ZIP_DEFLATED)
    for it in items:
        data = zin.read(it.filename)
        if it.filename.startswith('word/media/') and it.filename.lower().endswith('.png'):
            h = md5(data)
            if h in shot_md5:
                name = shot_md5[h]
                new_path = NEW[name]
                new_bytes = io.open(new_path, 'rb').read()
                old_w = Image.open(io.BytesIO(data)).size
                new_w = Image.open(io.BytesIO(new_bytes)).size
                assert new_w[0] == 2 * old_w[0] and new_w[1] == 2 * old_w[1], (name, old_w, new_w)
                data = new_bytes
                replaced.append((it.filename, name, old_w, new_w))
            else:
                unmatched.append(it.filename)
        else:
            untouched += 1
        zout.writestr(it, data)
    zout.close(); zin.close()
    print('已替换 %d 张截图，其余条目原样写出 %d 个' % (len(replaced), untouched))
    for fn, name, ow, nw in replaced:
        print('  %-16s ← %-28s %sx%s → %sx%s（%.0f → %.0f dpi@14.6cm）' % (fn, name, ow[0], ow[1], nw[0], nw[1], ow[0] / (14.6 / 2.54), nw[0] / (14.6 / 2.54)))
    print('未配对的内嵌 PNG %d 张（保持原样）：%s' % (len(unmatched), [os.path.basename(x) for x in unmatched[:6]]))
    print('输出：%s（%.1f MB）' % (DST, os.path.getsize(DST) / 1048576.0))


if __name__ == '__main__':
    main()