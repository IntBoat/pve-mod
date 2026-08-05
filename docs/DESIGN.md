# 設計與修改細節

## 目標與約束

- 在節點 Summary 顯示 **CPU Package 溫度**與 **風扇 RPM**
- 歷史圖使用與官方 **CPU Usage** 相同的 `proxmoxRRDChart`
- **不**改寫 `pvestatd`／官方 `pve-node-9.0` DS（避免弄壞既有曲線）
- **不**安裝 Meliox 全套感測器面板（避免全寬版面大改）
- 改動盡量可還原、可重套（標記字串 + 備份）

## 資料流

### 1. 採樣（collector）

腳本：[`bin/pve-sensors-update`](../bin/pve-sensors-update)

- 讀 `sensors -j`：
  - CPU：`coretemp` / `k10temp` / `zenpower` 的 `Package id 0` / `Tctl` / `Tdie`
  - Fan：所有 `fanN_input`，取 **最大值**（本機通常為 `fan2`）
- Fan 後備：直接讀 `/sys/class/hwmon/hwmon*/fan*_input`
- 寫入獨立 RRD（step 60s，RRA 對齊 PVE 9 常用解析）：

| RRD 路徑 | DS | 單位 |
|----------|-----|------|
| `/var/lib/rrdcached/db/pve-mod-cputemp/<node>` | `cputemp` | °C |
| `/var/lib/rrdcached/db/pve-mod-fanspeed/<node>` | `fanspeed` | RPM |

透過 `rrdcached` socket（若存在）更新。

systemd：`pve-sensors-update.timer` → 每分鐘執行 oneshot service。

### 2. API（Nodes.pm）

檔案：`/usr/share/perl5/PVE/API2/Nodes.pm`

#### status 即時欄位

在 `status` 方法 `return $res` 前注入：

- `cputemp`（number, °C）— 標記 `PVE_CPUTEMP_MOD`
- `fanspeed`（number, RPM）— 標記 `PVE_FANSPEED_MOD`

`returns.additionalProperties => 1`，可安全附加欄位。

#### 歷史資料 endpoint

| path | RRD |
|------|-----|
| `GET /nodes/{node}/cputemprrddata` | `pve-mod-cputemp/{node}` |
| `GET /nodes/{node}/fanspeedrrddata` | `pve-mod-fanspeed/{node}` |

參數與官方 `rrddata` 相同：`timeframe`、`cf`。

實作呼叫：

```perl
PVE::RRD::create_rrd_data("pve-mod-cputemp/$nodename", $timeframe, $cf);
PVE::RRD::create_rrd_data("pve-mod-fanspeed/$nodename", $timeframe, $cf);
```

`PVE::RRD` 會對任意 `/var/lib/rrdcached/db/<name>` 做 `RRDs::fetch`，無需改官方 RRD 模組。

子資源列表需註冊 `{ name => 'cputemprrddata' }`、`{ name => 'fanspeedrrddata' }`。

### 3. UI（pvemanagerlib.js）

檔案：`/usr/share/pve-manager/js/pvemanagerlib.js`

#### Model

```javascript
Ext.define('pve-rrd-cputemp', { fields: ['cputemp', time] });
Ext.define('pve-rrd-fanspeed', { fields: ['fanspeed', time] });
```

#### StatusView（`widget.pveNodeStatus`）

在 Manager Version 後增加兩列 `pmxInfoWidget`：

- CPU Temperature：進度條以 100°C 為滿刻度
- Fan Speed：進度條以 8000 RPM 為滿刻度；圖示使用 FA4 的 `fa-tachometer`

高度由 350 調整為約 410。

#### Summary 圖表

在 CPU Usage 圖後方插入兩個獨立 `Proxmox.data.RRDStore` + `proxmoxRRDChart`：

1. CPU Temperature → `/cputemprrddata`
2. Fan Speed → `/fanspeedrrddata`

`proxmoxRRDTypeSelector` 透過 Ext state `proxmoxRRDTypeSelection` 通知所有 `RRDStore`，因此切換 hour/day/… 時溫度／風扇圖會一併更新，無需改 selector。

activate / destroy 時對兩個 store 呼叫 `startUpdate` / `stopUpdate`。

## Patch 腳本

| 腳本 | 作用 |
|------|------|
| [`patches/apply-patches.py`](../patches/apply-patches.py) | 套用 CPU 溫度（若尚未有 `PVE_CPUTEMP_MOD`） |
| [`patches/apply-fan-patches.py`](../patches/apply-fan-patches.py) | 套用風扇（依賴或並存於 CPU patch；若尚未有 `PVE_FANSPEED_MOD`） |

兩者皆以字串錨點做精確插入，已套用則跳過。

## 硬體：ITE IT8613E

本機（Win Element M9 PRO / i7-1360P）`sensors-detect`：

```text
Chip `ITE IT8613E Super IO Sensors' @ 0xa30
Driver `to-be-written'
```

載入：

```bash
modprobe it87 force_id=0x8628
```

後可讀 `fan2_input`（RPM）與 PWM。設定檔見 [`modprobe/it87-fans.conf`](../modprobe/it87-fans.conf)。

## 風險與維護

1. **套件升級**：`pve-manager` 升級覆寫 `Nodes.pm` / `pvemanagerlib.js` → 重跑 `install.sh`
2. **歷史從部署起算**：獨立 RRD 不回溯官方資料
3. **還原**：`uninstall.sh` 還原 `.orig` 備份並停用 timer；RRD 與 it87 設定預設保留
4. **其他主機**：若已有原生 `nct6775` / `it87` 等，通常不需 `force_id`；collector 會自動讀任何 `fan*_input`
