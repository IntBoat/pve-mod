# pve-mod — Proxmox VE Summary 感測器擴充

在 PVE 節點 **Summary** 以最少改動加入：

1. **CPU Temperature**（即時進度條 + 歷史曲線，類似 CPU Usage）
2. **Fan Speed**（即時進度條 + 歷史曲線）

不修改官方 `pve-node-9.0` RRD schema，避免影響既有 CPU／記憶體等監控。

相容性：Proxmox VE **9.0–9.2**（以 9.2.5 驗證）。

---

## 架構

```text
sensors -j / hwmon
        │
        ▼
pve-sensors-update.timer (每 60 秒)
        │
        ├─► /var/lib/rrdcached/db/pve-mod-cputemp/<node>
        └─► /var/lib/rrdcached/db/pve-mod-fanspeed/<node>
                    │
                    ▼
        Nodes.pm API
          • status.cputemp / status.fanspeed
          • GET .../cputemprrddata
          • GET .../fanspeedrrddata
                    │
                    ▼
        pvemanagerlib.js Summary
          • StatusView 即時列
          • proxmoxRRDChart 歷史圖
```

詳見 [docs/DESIGN.md](docs/DESIGN.md)。

---

## 安裝（PVE 主機 root）

```bash
git clone git@git.zedo.dev:IntBoat/pve-mod.git
cd pve-mod
bash install.sh
```

然後對瀏覽器 **強制重新整理／清快取** 再開啟節點 Summary。

### 還原

```bash
bash uninstall.sh
```

---

## 目錄結構

| 路徑 | 說明 |
|------|------|
| `install.sh` / `uninstall.sh` | 安裝／還原 |
| `bin/pve-sensors-update` | 採樣腳本（寫入獨立 RRD） |
| `systemd/` | timer + oneshot service |
| `patches/apply-patches.py` | CPU 溫度：patch `Nodes.pm` + `pvemanagerlib.js` |
| `patches/apply-fan-patches.py` | 風扇速度：同上 |
| `modprobe/it87-fans.conf` | ITE IT8613E → `it87 force_id=0x8628` |
| `docs/DESIGN.md` | 修改細節與標記說明 |

---

## 會改動的 PVE 檔案

| 檔案 | 用途 |
|------|------|
| `/usr/share/perl5/PVE/API2/Nodes.pm` | `status` 加欄位；註冊 `cputemprrddata` / `fanspeedrrddata` |
| `/usr/share/pve-manager/js/pvemanagerlib.js` | StatusView 即時列 + Summary 圖表 |

標記字串（方便搜尋／升級後重套）：

- `PVE_CPUTEMP_MOD`
- `PVE_FANSPEED_MOD`

原始檔備份於 `/root/backup/pve-mod/`。

---

## 硬體注意（Win Element M9 PRO）

`sensors-detect` 可找到 **ITE IT8613E**，但核心尚無專用驅動。需：

```
options it87 force_id=0x8628
```

`install.sh` 會寫入 `/etc/modprobe.d/it87-fans.conf` 並 `modprobe`。成功後可見類似：

```text
it8628-isa-0a30
fan2:  5578 RPM
```

---

## 升級後

`pve-manager` 套件升級可能覆寫上述兩個檔案。重新執行：

```bash
bash install.sh
```

（腳本具冪等性：已套用的 patch 會跳過。）

---

## 驗證

```bash
sensors | grep -iE 'Package|fan'
systemctl status pve-sensors-update.timer
pvesh get /nodes/$(hostname -s)/status --output-format json | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('cputemp'), d.get('fanspeed'))"
pvesh get /nodes/$(hostname -s)/cputemprrddata --timeframe hour
pvesh get /nodes/$(hostname -s)/fanspeedrrddata --timeframe hour
```
