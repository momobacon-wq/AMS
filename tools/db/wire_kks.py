# -*- coding: utf-8 -*-
r"""tools/db/wire_kks.py — 接線路徑（KKS 版，v17）：GE 編號卡的接線路徑、迴路圖、電氣盤格位、訊號與供電，比照到「沒有 GE 編號、只有 KKS」的元件。

範圍：一號機的五份儀控電纜接線圖——HRSG HT1-1-ICE01-D1001、電氣 I&C D1002、BOP-WSC D1003（wire_epc 解析），加上燃機 D1004、汽機 D1005 上
認不出 GE 編號的那幾框（GE 編號的框是 wire_ge.json 的路徑，這裡不收）。網路圖 D1006 不收（盤對盤通訊，沒有現場元件）。
元件身分＝設備 KKS（訊號格 '=G11LBA30QM502XG01' 去掉訊號尾碼；鍵 'KKS|G11LBA30QM502'），機組照 KKS 的前三碼（G11、G12、S10、C10、C00…）。

做法：與 GE 版同一支 wire_ge.build（a.kks＝True 走 KKS 分支），輸出格式相同（paths／by_ge／jbs／sheets／stats），build_card_aux 與 pid_shots 照同一套讀：
  控制器 I/O：HRSG、BOP 的控制器（H11、H12、BOPE1、BOPM1A、BOPM1B、WSC1、SAMP1、AGC1；wire_epc.io_index），盤端子格只寫 'CA002 -2D1B 13'（沒有板名）——
    盤 KKS＋圖上的 CA 號 → 索引的（控制器, 櫃 LU001…）由 DeviceTag 投票定（wire_epc.assign_cab），板名照索引補上；BOPCM1、DWTC2 不在一號機索引（註記）。
  電纜表：A1001（HRSG）、A1002（電氣 I&C）、A1003（BOP-WSC，PDF 是 rev 0）——wire_epc.cable_schedule；PDF 上沒有的電纜號再查 A1003 的 xlsx（rev 1 較新）——wire_epc.cable_xlsx，只用來寫註記。
  位置：一號機儀器與接線箱位置圖 HT1-1-IIF01-D0001～D0006、D0008（KKS 標籤下一行是廠區座標，沿藍色引線找紅色符號）——接線箱、元件本身（hop 'devloc'）。
  電氣盤格位（EP24 MCC／PC）、其餘電氣盤（wire_ep）、訊號型式與供電（wire_sig＋wire_curated.json 的規則）沿用 GE 版。
人工註記：ge_tags_dir 的 wire_notes_kks.json（不進 repo；格式同 wire_notes.json，鍵 'KKS|<KKS>'，可加 '@p<頁>'）。

用法：
  py tools/db/wire_kks.py                                   # 寫 <CARDWORK>\wire_kks.json（rebuild.py 跟著 wire_ge 跑）
  py tools/db/wire_kks.py --verify "KKS|G11LBA30QM502"       # 另印這些條目的每一條路徑並畫疊框圖到 --verify-dir
"""
import argparse
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import pid_index as PI  # noqa: E402
import wire_ge as W  # noqa: E402

GENERATED_BY = 'tools/db/wire_kks.py'


def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    gdir = os.path.dirname(paths.GE_TAGS or '.')
    ap = argparse.ArgumentParser(description='接線路徑（KKS 版；見檔頭 docstring）')
    ap.add_argument('--library', default=paths.LIBRARY_ROOT, help='文件庫根目錄（預設 paths.LIBRARY_ROOT；唯讀）')
    ap.add_argument('--ge-tags', default=paths.GE_TAGS, help='GE 原廠編號對照表 ge_tags.json（燃機／汽機圖上 GE 編號的框要排除）')
    ap.add_argument('--notes', default=os.path.join(gdir, 'wire_notes_kks.json'), help='人工註記（預設 ge_tags.json 同目錄的 wire_notes_kks.json；不進 repo）')
    ap.add_argument('--curated', default=os.path.join(gdir, 'wire_curated.json'), help='人工查證資料（訊號型式與供電規則；與 GE 版共用）')
    ap.add_argument('--dcdas', default=paths.DCDAS_INDEX, help='signal-atlas 控制器索引（預設 paths.DCDAS_INDEX）；不存在就不核對 I/O 點')
    ap.add_argument('--text-cache', default=W.TEXT_CACHE, help='文字層字框快取目錄（與 wire_ge 共用）')
    ap.add_argument('--out', default=os.path.join(paths.CARDWORK, 'wire_kks.json'), help='輸出（預設 <CARDWORK>\\wire_kks.json）')
    ap.add_argument('--verify', metavar='KEY', nargs='+', help='另印這些條目（"KKS|G11LBA30QM502"）的每一條路徑、每一跳並畫疊框圖')
    ap.add_argument('--verify-dir', default=os.path.join(paths.AMS_LOCAL, 'wireverify_kks'), help='疊框圖輸出目錄')
    a = ap.parse_args()
    a.kks = True
    if not os.path.isdir(a.library):
        sys.exit('找不到文件庫：%s' % a.library)
    if not a.ge_tags or not os.path.exists(a.ge_tags):
        sys.exit('找不到 GE 編號對照表：%s' % a.ge_tags)
    out = W.build(a, print)
    out['generated_by'] = GENERATED_BY
    n = PI.write_json(a.out, out, 'wire_kks.json')
    st = out['stats']
    print('寫出 %s（%.2f MB）' % (os.path.basename(a.out), n / 1048576.0))
    print('KKS 元件 %d 個有接線路徑（%d 條路徑；文件 %s；機組 %s；控制器 %s）' % (st['located'], st['paths'], st['by_doc'], st['by_unit'], st['by_ctl']))
    print('畫法 %s；身分 %s；接線箱 %d（平面位置 %d）；元件位置 %d；電纜表 %d；圖紙 %d 張；註記 %d' % (
        st['by_mode'], st['by_via'], st['jbs'], st['jb_located'], st['devloc_paths'], st['room_paths'], st['sheets'], st['notes']))
    print('I/O 核對 %s' % {k: v for k, v in st['scan'].items() if k.startswith('io_')})
    print('旗標 %s' % st['flags'])
    if a.verify:
        W.verify(out, a.library, a.verify, a.verify_dir, print)


if __name__ == '__main__':
    main()
