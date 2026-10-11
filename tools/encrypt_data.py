# -*- coding: utf-8 -*-
"""Encrypt (or decrypt) a built data directory in place — the last step before stamping, for both sites.

  py tools/encrypt_data.py docs/data                 # plaintext sheets/*.json, card/*.json, manifest.json → <rel>.bin + meta.json
  py tools/encrypt_data.py docs/db/data
  py tools/encrypt_data.py docs/db/data --decrypt    # back to plaintext in place (rebuild card aux / verify with xlsx…)
  py tools/encrypt_data.py docs/db/data --decrypt-to <dir>   # plaintext copy elsewhere, ciphertext untouched
  py tools/encrypt_data.py docs/db/data --no-keep    # seal every file fresh (see「沿用沒變的密文」below)
  options: --key-file FILE  --fresh-salt  --no-keep  --dry-run

Scheme (same as momobacon-wq/signal-atlas; CONTRACT.md「加密與封裝」):
  key   = PBKDF2-HMAC-SHA256(passphrase, salt, 200000) → 32 bytes (AES-256-GCM)
  file  = <rel>.bin = 12-byte random IV || AES-GCM(gzip(JSON UTF-8, level 6, mtime 0)) with tag; AAD = rel (posix path
          relative to the data dir, without .bin) so a blob cannot be moved to another path
  meta.json (the only plaintext file) = {"enc":1,"gzip":1,"build":<manifest.build>,
          "kdf":{"name":"PBKDF2","hash":"SHA-256","iter":200000,"salt":<b64>},"check":<b64 seal(key,"ams-ok",aad="check")>}
Passphrase: env AMS_WEB_KEY, else line 1 of %LOCALAPPDATA%\\AMS\\web.key (or AMS_WEB_KEY_FILE / --key-file).  Line 2 of that
file holds the base64 16-byte salt: it is FIXED per installation (created on first run) so that a key remembered in the
browser (localStorage ams.key) survives rebuilds and is shared by docs/ and docs/db/ (same origin).  --fresh-salt rotates it.
`manifest.build` must already be computed on the plaintext (the generators do that); this tool never changes it.
The passphrase and key file never enter the repo.

== 沿用沒變的密文（compare-and-keep，2026-10-08）==
為什麼：IV 是隨機的，同一份明文每封一次密文就整份不同；舊版 encrypt_dir 又是「刪光 .bin、全部重封」，所以每次重建資料的
commit 都把全部密文重寫一遍（db 站 208 個 .bin 共 17.9 MB，內容沒變的也算）。密文不能做 delta 壓縮，這些全數進 .git
（2026-10-08 時 .git 已 286 MB）；P&ID 圖面影像加進來之後，每次重建會是約 30 MB。
作法：加密時向 git 要 HEAD 上同一路徑的密文；用**現在這把金鑰**、AAD＝rel 打得開，而且 gunzip 之後和新的明文**逐位元組相同**，
就把 HEAD 那份 .bin 原封不動寫回去，否則照舊以新的隨機 IV 重封。meta.json 的 check 同理：HEAD 的 kdf（salt／iter）相同、
check 用這把金鑰打得開就沿用 → 內容沒變的站重新加密後，git status 是乾淨的（meta.json 也逐位元組相同）。
  * 加密格式完全沒變（瀏覽器、decrypt_dir、verify_encrypted 都不必改）：沿用的那份本來就是合法密文，而且早已公開在 repo 裡。
    留下來的每一份都在當場以（金鑰、AAD＝rel）驗過並比對過明文，所以就算 git 回錯東西，最壞也只是少沿用幾份，不會寫出打不開
    或內容不對的 .bin。同一組（金鑰、IV）不會拿去封第二份明文：內容一變就重新抽 IV。
  * 比的是**明文**，不是 gzip 之後的位元組：zlib 換版、壓縮結果不同也照樣沿用（實測：HEAD 放一份 level 9 壓的密文，照樣留下）。
  * 來源是 **git HEAD**，不是工作目錄（原地解密時 .bin 已經刪掉了）：上一次建置還沒 commit 就再建一次，有變的檔會再重封一次，
    那不進歷史，無妨。HEAD 的密文一次問完：只開一個 `git cat-file --batch`（cwd＝資料目錄本身，物件名寫 `HEAD:./<rel>.bin`，
    git 自己由資料目錄往上找 repo），所以不管呼叫端的 cwd 在哪、是 rebuild.py／build_card_aux.py／extract_db.py／
    pneuvalve_site.py／extract.py 哪一支叫的都一樣。git 回的每一份先以它自己報的物件名驗過（物件名＝內容的雜湊）才收：
    HEAD 的 meta.json 現在會決定要不要擋下來（下一節），不能拿一份讀壞的回答來判斷。
  * 以下情形一律退回「全部重封」，不報錯：沒裝 git、資料目錄不在 git 工作區、HEAD 沒有這個路徑（新檔、第一次加密；
    rotate_passphrase.py 加密的是 data.rotate-tmp 副本，HEAD 本來就沒有）、個別舊密文打不開或不是這個路徑的、明文不同。結尾那行
    訊息會寫沿用幾份、重封幾份；一份都沒沿用時再附原因：[keep off]／[nothing for this dir at git HEAD]／
    [no file matches its git HEAD copy]／[key mismatch with git HEAD]（最後一種不是退回重封就算了，見下一節）。有沿用、只是 HEAD 的
    meta.check 用不上（HEAD 的 meta.json 讀不懂或 kdf 寫法不同）時，附的是中性的 [meta.check re-sealed]。
  * `--no-keep`＝全部重封；`--fresh-salt` 也一律全部重封。程式呼叫：encrypt_dir(..., keep=False)。
  * 代價（誠實說）：commit 歷史從此**確定**看得出「哪幾個檔這次有變」。以前其實也幾乎看得出來：AES-GCM 不改變長度、gzip 的結果
    是固定的，密文大小沒變的檔幾乎就是內容沒變的檔（稽核實測：到 0691d67 為止連續 8 組 commit、1,297 次同路徑比對，
    大小相同 1,146 次、明文相同 1,144 次——只有 2 次大小相同而內容有變，沒有內容相同而大小不同的）。內容仍然看不到。

== 這次的金鑰不是已發布的那一把：封完之後擋下來（2026-10-10）==
為什麼：key 檔第 2 行（salt）不見時（例：只從密碼管理員還原了密語），passphrase_and_salt() 會自己產生新的 salt 並寫回 key 檔；
AMS_WEB_KEY 給錯也一樣。加密照樣成功，整站改用另一把金鑰封，verify_encrypted 拿同一把金鑰去驗當然全過，沒有任何一關會紅。
後果上線才看得到：兩站共用瀏覽器的 ams.key，salt 一邊換了一邊沒換 → 同事在兩站之間切換就被重問密語；備品庫存的 STOCK_TOKEN
由金鑰算出，對不上之後領取／放入全部回「未授權」。舊版只在結尾那行附一個括號，exit 0。
條件（三個都成立才擋）：
  (1) keep 開著（不是 --no-keep／--fresh-salt／keep=False）；
  (2) git HEAD 上這個資料目錄有 meta.json，而且讀得懂（JSON、enc 為真、kdf.salt 是 16 bytes、check 的長度正確）；
  (3) 這次的金鑰（密語＋salt）打不開它的 check。
擋的方式：照常把整個目錄封完（用這次的金鑰；不能因為要擋就把明文留在 docs/ 底下）→ 印結尾那行 → raise SystemExit（非 0）。
訊息寫原因與三條出路。原因分得出來：salt 不同而密語是對的（拿 HEAD 的 salt 重算一把就打得開；訊息會印出已發布的 salt——它本來就
公開在 meta.json——照抄到 key 檔第 2 行即可）、密語不同、兩者都不同、KDF 參數不同。出路：(1) `git checkout -- <data>` 再
`git clean -fd -- <data>`（後者清掉 HEAD 沒有的 .bin）放棄這次建置；(2) 修正 AMS_WEB_KEY 或 key 檔（第 1 行密語、第 2 行 salt）後
做 (1) 再重建；(3) 確定是要換金鑰 → 目錄已經用新金鑰封好，戳記、驗證、commit 即可（手動加密時加 --no-keep 就不檢查）。
`--dry-run` 遇到同樣情形也印原因並以非 0 結束（什麼都沒寫）。
不會誤擋的正常流程（逐一實測，見下）：第一次加密、資料目錄不在 git 工作區、沒裝 git → HEAD 查無 meta.json；
rotate_passphrase.py → 它加密的是 data.rotate-tmp 副本，HEAD 沒有那個路徑；--no-keep／--fresh-salt → 不問 git。
**會擋，而且是故意的**：密語輪替完還沒 commit 就原地重建（HEAD 仍是舊金鑰的 meta.json）。先把輪替 commit 進去——
rotate_passphrase.py 結尾列的後續步驟本來就是跑完 E2E 就 push——之後的重建照常沿用。行程內呼叫 encrypt_dir 的產生器沒有
--no-keep 可下，所以在那之前要經 rebuild.py 重建是過不去的（會封好、然後停在這裡）。
各呼叫端遇到這個結束時，資料目錄已經是完整的密文（沒有 manifest.json、沒有明文）：
  * build_card_aux.py／extract_db.py／extract.py（行程內呼叫 encrypt_dir）：SystemExit 往外傳，後面的戳記不跑，行程以 1 結束。
    index.html／version.json 沒被動過，走出路 (1) 之後與 HEAD 一致。
  * rebuild.py：build_card_aux（或 pneuvalve_site）以非 0 結束 → 中止；它的失敗處理只在 manifest.json 還在時才再跑一次
    encrypt_data.py，這時已經不在，所以不會重跑，直接以非 0 結束。產生器先失敗、資料還是明文而它替你跑 encrypt_data.py 的那條路，
    金鑰不符時同樣封完再以非 0 結束（rebuild.py 不看那個結束碼，照樣把原本的錯誤往外丟）。
  * pneuvalve_site.py：成功路徑同 build_card_aux；它的失敗路徑（把原資料加密回去）也是封完才結束，但原本的錯誤會被這個
    SystemExit 蓋掉，「已把原資料加密回去」那行不會印。
  * rotate_passphrase.py 不會遇到（見上）；verify_encrypted.py／run_e2e.py／print_token.py 只借 passphrase_and_salt，不加密。
限制：靠的是 git HEAD。查不到 HEAD 的 meta.json（沒裝 git、git 逾時、資料目錄不在工作區、HEAD 那份讀不懂）就沒有這項保護，
結尾那行會是 [nothing for this dir at git HEAD]——在 repo 裡重建卻看到這句，一樣要停下來查。

== 寫檔順序（中斷後救得回來）==
先在記憶體把每一份密文備妥（到這裡資料目錄完全沒動）→ 先刪掉「與這次要寫的 .bin 只差大小寫」的舊 .bin → 寫全部 .bin（明文還在，
中斷就重跑）→ 刪掉沒有對應明文的舊 .bin → 寫 meta.json → 刪 manifest.json（這一刻起 is_encrypted() 為真）→ 刪其餘明文。
  * 只差大小寫的舊 .bin（2026-10-10）：在不分大小寫的檔案系統（Windows）上，新密文會寫進那個舊檔，檔名卻維持舊的大小寫，而密文的
    AAD 是新檔名 → decrypt_dir／瀏覽器拿磁碟上的檔名當 AAD 就打不開（InvalidTag）。先刪再寫就不會。現行流程碰不到（解密、
    build_card_aux、extract.py 都會先清掉舊 .bin），要「加密中斷之後，檔名又只改了大小寫」才會發生。
  * 刪明文那一步失敗（2026-10-10；檔案被別的程式開著、Ctrl-C）：以前整個中止，留下「is_encrypted() 為真、裡面還有明文」的目錄，
    再跑一次只印一句警告、exit 0。現在刪不掉的跳過、其餘照刪，最後以非 0 結束並列出剩下的檔。**同一個加密指令再跑一次就會收拾**：
    殘留的明文若與它的 .bin（用這個目錄 meta.json 的 salt＋密語打開、gunzip）逐位元組相同就刪掉；沒有 .bin、打不開、內容不同的
    一個都不動，列出來並以非 0 結束（那不是已經封存的內容，要人看過才能刪）。呼叫端原有的「is_encrypted → decrypt_dir →
    encrypt_dir」做法也照樣收拾得了（解密會把殘留的明文蓋成封存的內容）。
舊版是邊寫邊刪、而且一開始就刪光舊 .bin：中途失敗後再跑一次，會把已經封好的那些 .bin 當成「過期」刪掉，只剩還沒封到的檔
（實測：208 檔在第 101 個失敗，重跑後只剩 108 檔，訊息還是成功）。

實測（2026-10-08；git 2.52、Python 3.14.2〔zlib-ng 1.3.1〕；在獨立 clone 上做，HEAD 0691d67）：
  * db 站 208 檔、主站 42 檔：原地解密再加密 → git status 乾淨、meta.json 逐位元組相同，verify_encrypted 0 錯誤。
  * 改一個明文檔的一個字元 → 只有那個 .bin 變；產生器連 build 一起重算 → 那個檔＋manifest.json.bin＋meta.json（只差 build，check 沿用）。
  * 真的跑一次 tools/db/rebuild.py（當天重讀過的 drive_map）：只重封明文有變的 70 檔（2.7 MB），其餘 138 檔沿用；舊版是 208 檔
    17.9 MB 全寫。commit 之後輸入不變再跑一次：git status docs/ 是空的。
  * 時間（db 站，三次取中位數）：全部沿用 1.0 秒、--no-keep 1.5 秒、舊版 1.6 秒（沿用省掉 gzip 壓縮，反而快）；
    其中 git cat-file 0.13 秒、解開＋gunzip 208 份 0.09 秒。
  * 記憶體：第一段把全部密文放在記憶體，用量約是該站密文大小的 2～3 倍，不是 1 倍（稽核實測 333 檔、密文 28.0 MB：
    tracemalloc 峰值 64 MB、行程工作集峰值 90 MB——git 的整份輸出、逐份切出來的副本、新封的密文同時都在）。
  * 當天 HEAD 的 208 份密文，gzip 位元組與本機重壓的結果完全相同（比 gzip 位元組當天也行得通）；仍然比明文，換 Python／zlib 才不會整批失效。
實測（2026-10-10，上面「金鑰不符就擋下」與寫檔順序那兩點；同樣在獨立 clone 上做：HEAD 0691d67 的各呼叫端＋本檔，密語只用 key 檔的副本；
合成資料的幾組另在 Ubuntu 24.04／Python 3.12.3／git 2.43 重跑，結果相同）：
  * 金鑰不符：AMS_WEB_KEY 給錯 → db 站 208 檔全數以那把金鑰封好、沒有明文、exit 1，訊息有原因與三條出路；照訊息上的兩個 git 指令做完，
    git status 乾淨。key 檔少了第 2 行 → 同樣擋下，原因指明是 salt 並印出已發布的 salt；把它填回第 2 行、--decrypt 再加密 → 208 檔全數沿用、
    status 乾淨。經 rebuild.py：build_card_aux 封完以 1 結束，rebuild 中止、沒有再跑一次加密、沒有戳記；「資料本來就是明文而密語錯」與
    「產生器先失敗、由 rebuild 代跑加密」兩條路結果相同。pneuvalve_site.py 的成功與失敗兩條路、extract.py（主站 42 檔）也一樣。
    密語錯而站還是密文時，rebuild.py 在第一步解密就停，什麼都沒動。
  * 不誤擋：rotate_passphrase.py --dry-run 與真的輪替（兩站 250 檔，兩行結尾都是 [nothing for this dir at git HEAD]）、--fresh-salt、
    --no-keep、還沒有任何 commit 的 repo、HEAD 沒有的新目錄、git 工作區外、PATH 上沒有 git，全部 exit 0。
    輪替後還沒 commit 就原地解密再加密 → 擋（故意的）；加 --no-keep 就過，commit 之後不加也過。
  * git 的回答被動過（稽核那 126 種截斷／翻位元／張冠李戴，另加「只改 meta.json 裡 check 的一個字元」「只截掉結尾」）：沒有一次誤擋，
    結果都是完整、解得開的密文目錄。SHA-256 物件格式的 repo 也照樣沿用、照樣擋。
  * 刪明文失敗：sheets/30.json 被另一個 handle 開著（WinError 32）→ 其餘照刪、exit 1 並指名那個檔，目錄裡只剩它一個明文；同一個指令
    再跑一次 → 刪掉它、exit 0、git status 乾淨。殘留檔改過一個位元組的、沒有 .bin 的 → 指名、不動、exit 1。每一個檔案系統動作各壞一次的
    故障注入共 83 例：沒有一例遺失資料，重跑之後全部乾淨（修正前有 24 例重跑後明文還在）。
  * 只差大小寫的舊 .bin：磁碟上是新檔名、decrypt_dir 打得開（修正前 InvalidTag）。--dry-run 報的「stale .bin removed」與接著真的刪掉的
    數目相同（修正前把磁碟上每一個 .bin 都算進去）。
  * 沒有變的部分照舊：兩站原地解密再加密 → 208／42 檔全數沿用、status 乾淨；改一個字元只動一個 .bin；真的跑 rebuild.py 只重封明文有變的
    70 檔，commit 後再跑 status 是空的；時間也沒變（db 站全部沿用 1.06 秒、--no-keep 1.56 秒——每份回答多算一次 SHA-1，量不出差別）。
"""
import argparse
import base64
import gzip
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

KDF_ITER = 200_000
CHECK_TEXT = b"ams-ok"
CHECK_LEN = 12 + len(CHECK_TEXT) + 16  # meta.check 解 base64 之後一定是這個長度：IV＋密文＋GCM tag
KEY_STORE = "ams.key"  # localStorage name used by docs/assets/core.js (not atlas.key: same origin as signal-atlas)
GIT_TIMEOUT = 300      # 秒；git cat-file 逾時就當作 HEAD 沒有東西（全部重封）
GIT_LOCATION_ENV = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY", "GIT_INDEX_FILE", "GIT_PREFIX")
SHOW_NAMES = 5         # 錯誤訊息裡最多列幾個檔名（其餘只報數量）


def b64(b):
    return base64.b64encode(b).decode("ascii")


def default_key_file():
    p = os.environ.get("AMS_WEB_KEY_FILE")
    if p:
        return Path(p)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "AMS" / "web.key"


def passphrase_and_salt(key_file=None, fresh=False, persist=True):
    """(passphrase, salt).  Passphrase from AMS_WEB_KEY or line 1 of the key file; salt from line 2 (created/persisted on
    first use or with fresh=True)."""
    kf = Path(key_file) if key_file else default_key_file()
    lines = kf.read_text(encoding="utf-8").splitlines() if kf.exists() else []
    pw = (os.environ.get("AMS_WEB_KEY") or (lines[0] if lines else "")).strip()
    if not pw:
        raise SystemExit(f"site passphrase not found: set AMS_WEB_KEY or put it on line 1 of {kf}")
    if len(pw) < 8:
        raise SystemExit("site passphrase too short (min 8 characters)")
    salt = None
    if not fresh and len(lines) > 1 and lines[1].strip():
        try:
            salt = base64.b64decode(lines[1].strip())
        except Exception:
            salt = None
        if salt is not None and len(salt) != 16:
            salt = None
    if salt is None:
        salt = secrets.token_bytes(16)
        if persist:
            kf.parent.mkdir(parents=True, exist_ok=True)
            kf.write_text((lines[0] if lines else pw) + "\n" + b64(salt) + "\n", encoding="utf-8")
            print(f"[key] new salt written to {kf}")
        else:
            print("[key] WARNING: salt not persisted (remembered browser keys will not match next build)")
    return pw, salt


def derive_key(passphrase, salt):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=KDF_ITER).derive(passphrase.encode("utf-8"))


def seal(key, plain, aad):
    """12-byte random IV || AES-256-GCM ciphertext+tag (WebCrypto layout).  AAD = relative path (or 'check')."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    iv = secrets.token_bytes(12)
    return iv + AESGCM(key).encrypt(iv, plain, aad.encode("utf-8"))


def unseal(key, blob, aad):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key).decrypt(blob[:12], blob[12:], aad.encode("utf-8"))


def is_encrypted(data):
    data = Path(data)
    return (data / "meta.json").exists() and not (data / "manifest.json").exists()


def plain_files(data):
    return sorted(p for p in Path(data).rglob("*.json") if p.name != "meta.json")


def is_git_blob(oid, body):
    """body 是不是物件名 oid（bytes；SHA-1 repo 是 40 位 hex，SHA-256 repo 是 64 位）所指的 blob。
    git 的物件名＝hash("blob <長度>\\0" + 內容)，所以 `git cat-file --batch` 的每一份回答都能自己驗自己。"""
    h = hashlib.new("sha256" if len(oid) == 64 else "sha1", b"blob %d\0" % len(body) + body, usedforsecurity=False)
    return h.hexdigest().encode("ascii") == oid


def head_blobs(data, rels):
    """git HEAD 上、資料目錄 data 底下各相對路徑（posix）的檔案內容 → {rel: bytes}；HEAD 沒有的路徑不在回傳裡。
    只開一個 `git cat-file --batch`：cwd＝資料目錄，物件名 `HEAD:./<rel>`（`./` ＝相對於 cwd，git 自己往上找 repo 根目錄），
    所以與呼叫端的 cwd 無關；GIT_DIR／GIT_WORK_TREE 這類「指定 repo 位置」的環境變數（從 git hook、rebase --exec 裡被叫到時
    會帶著）先拿掉，否則 `./` 會被當成相對於 repo 根目錄而全部查無。沒裝 git、不在工作區、沒有 HEAD、逾時、輸出對不上
    → 一律回 {}（呼叫端就全部重封）；git 的錯誤訊息不外流。
    每一份都以 git 報的物件名驗過（is_git_blob）才收，長度不足、內容被動過的就當作 HEAD 沒有那個路徑：回傳的 meta.json 會被
    encrypt_dir 拿來判斷「金鑰是不是已發布的那一把」，不能用一份讀壞的回答去擋人。至於各 .bin，encrypt_dir 仍會逐份以
    金鑰＋AAD 驗過、比對明文才沿用。"""
    rels = [r for r in rels if "\n" not in r]  # 一行一個物件名；檔名含換行的（不會有）就不問
    git = shutil.which("git")
    if not git or not rels:
        return {}
    env = {k: v for k, v in os.environ.items() if k not in GIT_LOCATION_ENV}
    try:
        r = subprocess.run([git, "cat-file", "--batch"], cwd=str(data), env=env, timeout=GIT_TIMEOUT,
                           input="".join(f"HEAD:./{x}\n" for x in rels).encode("utf-8"),
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        out, pos, got = r.stdout, 0, {}
        for rel in rels:  # 回應與要求一對一、同順序：「<物件名> <type> <size>\n<內容>\n」或「<要求的名字> missing\n」
            nl = out.index(b"\n", pos)
            head, pos = out[pos:nl], nl + 1
            if head.endswith(b" missing"):
                continue
            oid, typ, size = head.split(b" ")
            size = int(size)
            body = out[pos:pos + size]
            if typ == b"blob" and len(body) == size and is_git_blob(oid, body):
                got[rel] = body
            pos += size + 1
        return got
    except Exception:
        return {}


def head_key_state(head_meta, passphrase, salt, key, kdf):
    """git HEAD 的 meta.json（bytes；HEAD 沒有就是 None）對上這次的金鑰 → (check, mismatch)。
    check：HEAD 的 kdf（salt／iter…）與這次相同、而且用這把金鑰打得開 → 回原字串（沿用它，內容沒變的站 meta.json 才會逐位元組
    相同），否則 None（重新封一個）。
    mismatch：HEAD 那份是讀得懂的加密站 meta（JSON、enc 為真、kdf.salt 16 bytes、check 長度正確），而這次的金鑰打不開它的 check
    → 一句原因（英文 ASCII，會進 key_mismatch_message；encrypt_dir 在整個目錄封完之後才擋）。HEAD 沒有 meta.json、讀不懂、
    或打得開 → None。HEAD 的 salt 是公開的，所以分得出是哪一種不同：拿它重算一把金鑰，打得開就是「密語對、salt 不對」。"""
    try:
        m = json.loads(head_meta.decode("utf-8"))
        hk = m["kdf"]
        hsalt = base64.b64decode(hk["salt"])
        chk = base64.b64decode(m["check"])
        if not m.get("enc") or len(hsalt) != 16 or len(chk) != CHECK_LEN:
            return None, None
    except Exception:  # None 或讀不懂：談不上「金鑰不符」，只是沒有 check 可沿用
        return None, None

    def opens(k):
        try:
            return unseal(k, chk, "check") == CHECK_TEXT
        except Exception:
            return False

    if opens(key):
        return (m["check"] if hk == kdf else None), None
    pub = b64(hsalt)
    if any(hk.get(f) != kdf[f] for f in ("name", "hash", "iter")):
        return None, "the KDF parameters in the meta.json at git HEAD (%s) are not the ones this tool uses" % ", ".join(
            ascii(hk.get(f)) for f in ("name", "hash", "iter"))
    if hsalt == salt:
        return None, "the passphrase of this run is not the one the published site was sealed with (the salt is the same)"
    if opens(derive_key(passphrase, hsalt)):
        return None, ("the passphrase is the published one but the salt is not: this run used %s, the published site has %s\n"
                      "         -> line 2 of the key file must be %s" % (kdf["salt"], pub, pub))
    return None, "neither the passphrase nor the salt of this run is the published one (published salt: %s)" % pub


def key_mismatch_message(data, cause, dry_run=False, stuck=0):
    """金鑰不符（檔頭「這次的金鑰不是已發布的那一把」）的結束訊息：發生了什麼、原因、三條出路。
    全 ASCII：它經 SystemExit 印到 stderr，Windows 主控台是 cp950。stuck＝封完之後還刪不掉的明文數（另有一段訊息列出）。"""
    d = str(data)
    if dry_run:
        return ("[encrypt] STOP - key mismatch (dry run, nothing written): the key of this run does not open the meta.json of\n"
                f"  {d} at git HEAD (the published site).\n"
                f"  cause: {cause}\n"
                "  A real run would seal the directory with this key and then stop with the same message.\n"
                "  Correct env AMS_WEB_KEY or the key file (line 1 passphrase, line 2 salt); if the new key is intended, use --no-keep.")
    left = ("no plaintext is left" if not stuck else
            f"{stuck} plaintext .json could not be deleted - see above")
    return (f"[encrypt] STOP - key mismatch: {d} is now sealed with a key that does not open the meta.json at git HEAD\n"
            "  (the published site).\n"
            f"  cause: {cause}\n"
            f"  Every file is sealed with the key of THIS run ({left}), so the directory is consistent - but it is not the\n"
            "  published key.  Do not commit or push it as it is: remembered browser keys and the stock token would stop working.\n"
            "  Ways out:\n"
            "   1. discard this build, back to the published ciphertext (the 2nd command removes the .bin git HEAD does not have):\n"
            f"        git checkout -- \"{d}\"\n"
            f"        git clean -fd -- \"{d}\"\n"
            "   2. the key was wrong: correct env AMS_WEB_KEY or the key file (line 1 passphrase, line 2 salt), do 1, build again.\n"
            "      To keep this build instead: --decrypt with the key exactly as it is now, correct the key, encrypt again, stamp.\n"
            "   3. the new key is intended (e.g. a rotation that is not committed yet): nothing to redo, the directory is sealed\n"
            "      with it - stamp, verify and commit; later builds keep again.  Encrypting by hand with --no-keep skips this check.\n"
            "  (stamp + verify, both sites: py tools/db/rebuild.py --only-stamp)")


def name_list(data, paths):
    """錯誤訊息用：前 SHOW_NAMES 個相對路徑，其餘只報數量。"""
    rels = [p.relative_to(data).as_posix() for p in paths]
    return ", ".join(rels[:SHOW_NAMES]) + (f" ... (+{len(rels) - SHOW_NAMES} more)" if len(rels) > SHOW_NAMES else "")


def os_error_text(e):
    """OSError 的一句 ASCII 描述（Windows 的 strerror 是中文，不放進會印到 cp950 stderr 的訊息裡）。"""
    code = getattr(e, "winerror", None)
    return type(e).__name__ + (f" [WinError {code}]" if code else f" [errno {e.errno}]" if e.errno else "")


def sweep_leftovers(data, passphrase, left, log=print, dry_run=False):
    """已經加密的目錄裡殘留的明文（上一次在刪明文途中中斷才會有；left＝plain_files(data)）。
    金鑰用這個目錄 meta.json 的 salt＋密語（load_key；密語打不開 check 就在動任何檔之前結束）——不看 key 檔的 salt，它可能正是
    出錯的那個。殘留檔的 .bin 打得開（AAD＝rel）而且 gunzip 之後與它逐位元組相同 → 那份明文已經完整封存，刪掉。
    其餘（沒有 .bin、打不開、內容不同、刪不掉）一個都不動，列出來並 raise SystemExit：那不是已經封存的內容，不能替人決定。"""
    key, meta = load_key(data, passphrase, tag="encrypt")
    same, differ, nobin, stuck = [], [], [], []
    for p in left:
        rel = p.relative_to(data).as_posix()
        q = data / (rel + ".bin")
        if not q.exists():
            nobin.append(p)
            continue
        try:
            b = unseal(key, q.read_bytes(), rel)
            ok = (gzip.decompress(b) if meta.get("gzip", 1) else b) == p.read_bytes()
        except Exception:  # 打不開（不是這把金鑰／這個路徑的密文）或不是 gzip：與「內容不同」同樣處理
            ok = False
        (same if ok else differ).append(p)
    if not dry_run:
        for p in same:
            try:
                p.unlink(missing_ok=True)
            except OSError as e:
                stuck.append((p, e))
    n_gone = len(same) - len(stuck)
    log(f"[encrypt] {data}: already encrypted (no manifest.json); {'would remove' if dry_run else 'removed'} {n_gone} leftover "
        f"plaintext .json identical to the sealed copy" + ("" if not (differ or nobin or stuck) else
                                                           f"; {len(differ) + len(nobin) + len(stuck)} NOT removed"))
    if not (differ or nobin or stuck):
        return None
    msg = [f"[encrypt] {data}: already encrypted, but plaintext .json is still in it that was not removed:"]
    if differ:
        msg.append(f"  {len(differ)} differ from their .bin (or the .bin does not open): {name_list(data, differ)}")
    if nobin:
        msg.append(f"  {len(nobin)} have no .bin at all: {name_list(data, nobin)}")
    if differ or nobin:
        msg.append("  These are NOT what is sealed (the .bin is what git and the site have).  Nothing was done to them: look at them,\n"
                   "  delete the stale ones by hand; to publish them instead, move them out, --decrypt, put them back and run the\n"
                   "  generator again (manifest.build has to be recomputed), which encrypts at its end.")
    if stuck:
        msg.append(f"  {len(stuck)} are identical to their .bin but could not be deleted ({os_error_text(stuck[0][1])}): "
                   f"{name_list(data, [p for p, _ in stuck])}\n"
                   "  Close whatever has them open and run the same command again.")
    raise SystemExit("\n".join(msg))


def encrypt_dir(data, passphrase, salt, log=print, dry_run=False, keep=True):
    """Plaintext data dir → ciphertext in place.  Returns meta dict (None when already encrypted).
    keep=True：內容沒變的檔沿用 git HEAD 的密文（見檔頭「沿用沒變的密文」）；keep=False：每個檔都以新的隨機 IV 重封。
    以 SystemExit（非 0）結束的三種情形，前兩種發生時目錄都已經封好：(a) keep=True 而這次的金鑰打不開 git HEAD 的 meta.check
    （檔頭「這次的金鑰不是已發布的那一把」）；(b) 有明文刪不掉；(c) 目錄已加密、裡面殘留的明文與封存的內容不同（sweep_leftovers）。"""
    data = Path(data)
    man_p = data / "manifest.json"
    if not man_p.exists():
        if (data / "meta.json").exists():
            left = plain_files(data)  # 上次在刪明文途中中斷才會有：.bin 與 meta.json 都已寫好
            if left:
                return sweep_leftovers(data, passphrase, left, log=log, dry_run=dry_run)
            log(f"[encrypt] {data}: already encrypted (no manifest.json) — nothing to do")
            return None
        raise SystemExit(f"[encrypt] {data}: manifest.json not found")
    man = json.loads(man_p.read_bytes().decode("utf-8"))
    build = man.get("build")
    if not build:
        raise SystemExit("[encrypt] manifest.json has no build (run the generator / data_build first)")
    files = plain_files(data)
    rels = [p.relative_to(data).as_posix() for p in files]
    stale = sorted(data.rglob("*.bin"))
    targets = {data / (rel + ".bin"): rel + ".bin" for rel in rels}  # 這次要寫的 .bin → 它確切的相對路徑（大小寫照明文檔名）
    key = derive_key(passphrase, salt)
    kdf = {"name": "PBKDF2", "hash": "SHA-256", "iter": KDF_ITER, "salt": b64(salt)}
    head = head_blobs(data, [r + ".bin" for r in rels] + ["meta.json"]) if keep else {}
    check, mismatch = head_key_state(head.get("meta.json"), passphrase, salt, key, kdf)

    # ---- 第一段：每個檔的密文先在記憶體備妥（沿用或重封）。到這裡為止資料目錄一個位元組都沒動，任何失敗都還是完整的明文目錄
    blobs = []
    kept = plain = wire = new_b = 0
    for p, rel in zip(files, rels):
        b = p.read_bytes()
        blob = None
        old = head.get(rel + ".bin")
        if old is not None:
            try:  # 沿用的條件＝瀏覽器解這個路徑會得到的東西與新明文完全相同
                if gzip.decompress(unseal(key, old, rel)) == b:
                    blob = old
            except Exception:  # 打不開（換過密語／salt、不是這個路徑的密文）或不是 gzip → 重封
                pass
        if blob is not None:
            kept += 1
        elif not dry_run:
            blob = seal(key, gzip.compress(b, 6, mtime=0), rel)
            new_b += len(blob)
        plain += len(b)
        if blob is not None:
            wire += len(blob)
            blobs.append((rel, blob))
    n = len(files)
    if kept:  # 有沿用就不附「為什麼沒沿用」；只有 HEAD 的 check 用不上時留一個中性的註記
        why = "" if check else " [meta.check re-sealed]"
    elif not keep:
        why = " [keep off]"
    elif not head:
        why = " [nothing for this dir at git HEAD]"
    elif mismatch:
        why = " [key mismatch with git HEAD]"
    else:
        why = " [no file matches its git HEAD copy]"
    if mismatch and kept:  # HEAD 的 meta.check 打不開、同一個 HEAD 的密文卻打得開：HEAD 本身前後不一，照樣擋，原因裡講明
        mismatch += f"\n         (yet {kept} of the .bin at git HEAD do open with this key: git HEAD itself is inconsistent)"
    if dry_run:
        gone = sum(1 for q in stale if q not in targets)  # 只算真的會被刪掉的（沒有對應明文的）；其餘是被覆寫
        log(f"[encrypt] dry run: {n} files would be encrypted ({kept} kept from git HEAD, {n - kept} sealed fresh{why}), "
            f"{gone} stale .bin removed, build {build}")
        if mismatch:
            raise SystemExit(key_mismatch_message(data, mismatch, dry_run=True))
        return None

    # ---- 第二段：寫檔。順序＝中斷在任何一步都救得回來（見檔頭）
    for q in stale:  # 與這次要寫的 .bin 只差大小寫的舊檔：先刪，否則新密文會寫進舊檔名（不分大小寫的檔案系統；Path 比對在 Windows 也不分）
        if q in targets and q.relative_to(data).as_posix() != targets[q]:
            q.unlink()
    for rel, blob in blobs:
        (data / (rel + ".bin")).write_bytes(blob)
    for q in stale:  # 沒有對應明文的舊 .bin
        if q not in targets:
            q.unlink()
    meta = {"enc": 1, "gzip": 1, "build": build, "kdf": kdf,
            "check": check or b64(seal(key, CHECK_TEXT, "check"))}
    (data / "meta.json").write_text(json.dumps(meta, separators=(",", ":")), encoding="utf-8", newline="\n")
    man_p.unlink()  # 這一刻起 is_encrypted() 為真
    stuck = []      # 刪不掉的明文（被別的程式開著…）：跳過、其餘照刪，最後一起報；再跑一次由 sweep_leftovers 收拾
    for p in files:
        if p != man_p:
            try:
                p.unlink(missing_ok=True)
            except OSError as e:
                stuck.append((p, e))
    log(f"[encrypt] {data}: {n} files  {plain / 1e6:.1f} MB → {wire / 1e6:.1f} MB on the wire  build {build}  "
        f"({kept} kept from git HEAD, {n - kept} sealed fresh = {new_b / 1e6:.1f} MB new{why})")
    stop = []
    if stuck:
        stop.append(f"[encrypt] {data}: sealed, but {len(stuck)} plaintext .json could not be deleted ({os_error_text(stuck[0][1])}): "
                    f"{name_list(data, [p for p, _ in stuck])}\n"
                    "  The directory still holds plaintext.  Close whatever has these files open and run the same encrypt command\n"
                    "  again: it removes leftovers that are identical to their sealed copy.")
    if mismatch:
        stop.append(key_mismatch_message(data, mismatch, stuck=len(stuck)))
    if stop:
        raise SystemExit("\n".join(stop))
    return meta


def load_key(data, passphrase, tag="decrypt"):
    """Key for an encrypted dir: salt from its meta.json; verifies the passphrase against meta.check.
    tag＝訊息開頭的方括號（sweep_leftovers 是在加密指令裡叫的）。meta.json 本身壞掉（缺 kdf.salt／check、不是 base64、長度不對）
    與「密語打不開」分開報：前者換哪個密語都沒用，要把 meta.json 救回來。"""
    meta = json.loads((Path(data) / "meta.json").read_text(encoding="utf-8"))
    if not meta.get("enc"):
        raise SystemExit(f"[{tag}] meta.json says enc:0 (plaintext export)")
    try:
        salt = base64.b64decode(meta["kdf"]["salt"])
        check = base64.b64decode(meta["check"])
        if len(check) != CHECK_LEN:
            raise ValueError("check length")
    except Exception:
        raise SystemExit(f"[{tag}] meta.json is damaged (kdf.salt / check missing, not base64 or of the wrong length): "
                         "no passphrase can open it - restore meta.json (git checkout)")
    key = derive_key(passphrase, salt)
    try:  # 密語不對時 AES-GCM 丟 InvalidTag：改成一行訊息結束（此時什麼都還沒動），不要噴 traceback
        ok = unseal(key, check, "check") == CHECK_TEXT
    except Exception:
        ok = False
    if not ok:
        raise SystemExit(f"[{tag}] passphrase does not open meta.check")
    return key, meta


def decrypt_dir(data, passphrase, out=None, log=print):
    """Ciphertext → plaintext.  out=None: in place (removes .bin and meta.json); else write the plaintext copy under out."""
    data = Path(data)
    key, meta = load_key(data, passphrase)
    n = 0
    for p in sorted(data.rglob("*.bin")):
        rel = p.relative_to(data).as_posix()[:-4]
        b = gzip.decompress(unseal(key, p.read_bytes(), rel)) if meta.get("gzip", 1) else unseal(key, p.read_bytes(), rel)
        dst = (Path(out) if out else data) / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(b)
        if out is None:
            p.unlink()
        n += 1
    if out is None:
        (data / "meta.json").unlink()
    log(f"[decrypt] {data}: {n} files → {out or data}")
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("data_dir")
    ap.add_argument("--key-file")
    ap.add_argument("--decrypt", action="store_true", help="ciphertext → plaintext in place")
    ap.add_argument("--decrypt-to", metavar="DIR", help="plaintext copy under DIR (ciphertext kept)")
    ap.add_argument("--fresh-salt", action="store_true", help="rotate the salt (remembered browser keys stop working); implies --no-keep")
    ap.add_argument("--no-keep", action="store_true",
                    help="seal every file with a fresh IV instead of keeping the git HEAD ciphertext of files whose plaintext did not change; "
                         "also skips the check that this run's key opens the meta.json at git HEAD")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    data = Path(a.data_dir)
    if not data.is_dir():
        raise SystemExit(f"not a directory: {data}")
    if a.decrypt or a.decrypt_to:
        pw, _ = passphrase_and_salt(a.key_file, persist=False)
        decrypt_dir(data, pw, out=a.decrypt_to)
        return 0
    pw, salt = passphrase_and_salt(a.key_file, fresh=a.fresh_salt, persist=not a.dry_run)
    encrypt_dir(data, pw, salt, dry_run=a.dry_run, keep=not (a.no_keep or a.fresh_salt))
    return 0


if __name__ == "__main__":
    sys.exit(main())
