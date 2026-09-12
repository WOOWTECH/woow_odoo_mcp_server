# charts/odoo-mcp

單一 Odoo 租戶 MCP server 的 K3s Helm chart，取代原本放在 repo 根目錄的
`k8s-deploy.yaml`。那份檔案只是某次手動套用到單一 namespace（`kasim-odoo`）的
manifest 副本，引用的 image 不是本 repo 建的，而且早就和所有正在跑的租戶對不上了。

[English](README.md)

一個 Odoo instance 一個 release。這個 chart 不碰租戶本身：Odoo、PostgreSQL 和
Cloudflare Tunnel 都維持原狀。

---

## 佈署內容

| 物件 | 名稱 | 用途 |
|---|---|---|
| Deployment + Service | `mcp-odoo` | `python3 -m odoo_mcp`，streamable HTTP 在 `:8000/mcp`，啟動前先套用 `patches/*.py` |
| Deployment + Service | `mcp-odoo-proxy` | nginx token 閘門：只有 `/private_<token>/…` 會轉發，其餘一律 `403` |
| ConfigMap | `mcp-odoo-proxy-config` | nginx 設定（含 token，**預設不由 chart 產生**） |
| ConfigMap | `mcp-odoo-policy` | `odoo_mcp_policy.json`，副作用白名單 |
| ConfigMap | `mcp-odoo-patch` | 三支 WOOWTECH patch，掛在 `/app/patches` |
| PersistentVolumeClaim | `mcp-admin-data` | `/data`（選用） |
| Deployment + Service | `mcp-odoo-admin` | 本 repo 的 FastAPI 管理後台（選用，預設關閉） |
| Secret | `mcp-odoo-secrets`、`mcp-odoo-admin-secret` | 只有 `secrets.create=true` 才產生 |
| NetworkPolicy | `mcp-odoo-deny-external` | 選用，預設關閉 |

`baseName` 可以一次改掉全部名稱（同租戶第二個資料庫的 MCP 用
`baseName: mcp-odoo-social`）。

---

## 安裝

clone 之後：

```bash
helm install mcp-odoo charts/odoo-mcp -n <tenant> \
  -f charts/odoo-mcp/deploy/woow-k3s/<tenant>.yaml
```

不 clone，直接用 GitHub tarball。chart 放在子目錄，所以要先解開：
`helm install <url>` 只吃 `Chart.yaml` 在壓縮檔根目錄的 chart，而 GitHub 的
原始碼壓縮檔根目錄永遠不是 chart：

```bash
REF=main   # 任何 branch 或 tag
curl -fsSL "https://github.com/WOOWTECH/woow_odoo_mcp_server/archive/refs/heads/${REF}.tar.gz" | tar -xz
# GitHub 會用 ref 當解開後的目錄名，並把 / 換成 -
CHART="woow_odoo_mcp_server-${REF//\//-}/charts/odoo-mcp"

helm install mcp-odoo "$CHART" -n <tenant> \
  -f "$CHART/deploy/woow-k3s/<tenant>.yaml"
```

用 tag 的話換成 `archive/refs/tags/${REF}.tar.gz`。CI 每次 push 都會重跑這條
「解開再安裝」的路徑，所以這段指令不會腐爛。

全新租戶，由 chart 產生憑證和 nginx 設定：

```bash
ODOO_PASSWORD=...            # MCP 用來登入 Odoo 的密碼
MCP_AUTH_TOKEN=$(python3 -c 'import secrets;print(secrets.token_hex(10))')

helm install mcp-odoo charts/odoo-mcp -n <tenant> --create-namespace \
  --set odoo.url=https://<tenant>-odoo.woowtech.io \
  --set odoo.db=<tenant> \
  --set "server.allowedHosts={<tenant>-mcp-odoo.woowtech.io,localhost,mcp-odoo-proxy.<tenant>.svc.cluster.local,mcp-odoo.<tenant>.svc.cluster.local,127.0.0.1}" \
  --set secrets.create=true --set secrets.odooPassword="$ODOO_PASSWORD" \
  --set proxy.config.create=true --set proxy.config.authToken="$MCP_AUTH_TOKEN"
```

MCP 端點會是
`http://mcp-odoo-proxy.<tenant>.svc.cluster.local:8001/private_<token>/mcp`，
也就是租戶 Cloudflare Tunnel 指過去的位置。

### 主要 values

| Value | 預設 | 說明 |
|---|---|---|
| `odoo.url`、`odoo.db` | — | **必填**，沒有預設值 |
| `server.allowedHosts` | `[]` | **必填**；空清單會讓每個請求都卡在 DNS rebinding 檢查 |
| `baseName` | `mcp-odoo` | 所有物件的名稱前綴 |
| `namespace.create` / `.name` | `false` / release ns | 等於 release namespace 的 namespace 永遠不會被 render |
| `keepOnUninstall` | `true` | 在 Namespace、PVC、chart 產生的 Secret 加上 `helm.sh/resource-policy: keep` |
| `storageClassName` | `longhorn` | 測試用 `longhorn-delete`，本機叢集用 `local-path` |
| `secrets.create` | `false` | `true` 時才從 `required()` 保護的 values 產生 Secret |
| `proxy.config.create` | `false` | `true` 時才用 `proxy.config.authToken` 產生 nginx ConfigMap |
| `persistence.enabled` | `false` | `/data` PVC（正式租戶是 1 Gi Longhorn） |
| `initConfig.enabled` | `false` | 從既有 ConfigMap 播種 `/data/config.json`，需要 `persistence.enabled` |
| `admin.enabled` | `false` | `:8080` 的 FastAPI 管理後台 |
| `networkPolicy.enabled` | `false` | 正式租戶已經有 namespace 層級的 policy |
| `server.podAnnotations` | `{}` | 用來帶入正式環境的 `kubectl.kubernetes.io/restartedAt` 標記 |

完整清單和註解在 [`values.yaml`](values.yaml)。

### 祕密

預設是 `secrets.create: false`：chart 只**引用**已經存在的 Secret，所以任何
upgrade 都不可能用空字串蓋掉真的密碼。欄位和佔位字串見
[`examples/secrets.example.yaml`](examples/secrets.example.yaml)。

有兩樣東西永遠不進 git：

* Odoo 密碼 — Secret `mcp-odoo-secrets` 的 `odoo-password`；
* MCP proxy token — 它是 nginx `location /private_<token>/` 的一部分，所以
  `proxy.config.create` 預設 `false`，chart 只掛叢集裡既有的 ConfigMap。
  見 [`examples/proxy-token.example.yaml`](examples/proxy-token.example.yaml)。

正式租戶的 `/data/config.json`（ConfigMap `mcp-admin-config`）裡是明文的後台密碼、
MCP token 和 Odoo 密碼。chart 只**掛載**它，不會產生它。改成 Secret 列在後續工作。

---

## 驗證

```bash
kubectl -n <tenant> rollout status deploy/mcp-odoo
kubectl -n <tenant> rollout status deploy/mcp-odoo-proxy
helm test mcp-odoo -n <tenant> --logs
```

`helm test` 跑一個唯讀 smoke pod：MCP server 在 `:8000` 有回應、proxy 沒 token 回
`403`、帶 token 的 `/private_<token>/mcp` 會被轉發、後台啟用時 `GET /healthz` 回
200。token 是從掛進去的 ConfigMap 讀的，所以不會出現在 pod spec 或 audit log 裡。

---

## 解除安裝（資料保留）

```bash
helm uninstall mcp-odoo -n <tenant>
```

`keepOnUninstall: true`（預設）會讓 Namespace、PVC 和 chart 產生的 Secret 帶著
`helm.sh/resource-policy: keep` 留下來，只有 Deployment、Service 和 policy/patch
ConfigMap 會消失。Odoo 租戶完全不受影響：chart 從來沒擁有過 Odoo、PostgreSQL 或
tunnel。要連資料一起清掉，事後自己刪 PVC。

---

## 接管正在跑的租戶

正式租戶是 `kubectl apply` 建的，不是 Helm。chart render 出來的物件和它們**一模一樣**，
所以接管不會重啟任何東西：

```bash
CONTEXT=woow-k3s NAMESPACE=komibright RELEASE=mcp-odoo scripts/check-drift.sh
```

會讀出正式物件，逐欄位和 `helm template … -f deploy/woow-k3s/komibright.yaml`
比對（兩邊都先正規化掉 API server 補的預設值，輸出裡的 proxy token 會被遮蔽）。
每個物件會回報 `SAME`、`INTENDED`（只有宣告過、有理由的差異）、`DRIFT`（連差在哪個
欄位一起印出來）或 `MISSING`。接著還有一道反方向的檢查：每個正式環境裡的 `mcp-*`
物件都必須落在「已比對」或 `REFERENCED`（chart 只掛名字、刻意不擁有的
`mcp-admin-config`、`mcp-odoo-proxy-config`、`mcp-admin-ghcr`、`mcp-odoo-secrets`），
否則會被報成 `UNCOVERED` 並讓腳本失敗——chart 漏掉某個物件就藏不住。

komibright 目前的結果：**7 個 SAME/INTENDED + 4 個 REFERENCED，exit 0**；把正式
token 傳進來（`--set proxy.config.create=true --set proxy.config.authToken=…`）
連 nginx ConfigMap 一起比就是 8/8。

唯一一項刻意的差異：PVC 多了 `helm.sh/resource-policy: keep`。它是 metadata
annotation，不會動到 pod template，也不會 roll 任何東西。

比對乾淨之後再接管：

```bash
helm upgrade --install mcp-odoo charts/odoo-mcp -n <tenant> \
  -f charts/odoo-mcp/deploy/woow-k3s/<tenant>.yaml --take-ownership
```

接著確認沒有 pod 重啟（`kubectl get pods -o wide`，比對前後的 UID 和 restart 次數）。

### Instance values

`deploy/woow-k3s/<tenant>.yaml` 是單一租戶的 values，不含祕密。目前只有
**komibright**，也就是標準形狀。

其他租戶在套用之後各自漂移了（env 子集不同、用 `emptyDir` 而不是 PVC、proxy volume
叫 `conf` 不叫 `config`、有些有套 patch 有些沒有）。要接管某個租戶之前，得先寫出它的
values 檔並讓 `check-drift.sh` 回報乾淨；如果漂移只是形式上的差異，先把正式物件正規化
反而是比較小的改動。

---

## 後續工作（刻意不放進這版 chart）

以下每一項都會動到正在跑的 pod template，所以維持 opt-in 且預設關閉：

1. **`/data/config.json` 把憑證放在 ConfigMap 裡。** `initConfig.keepExisting: true`
   至少能阻止每次重啟把輪替過的後台密碼和 MCP token 退回舊值；真正的修法是把這個檔案
   移到 Secret。
2. **`:latest` 配 `imagePullPolicy: Always`。** GHCR 上只有 `latest`，任何重啟都可能
   悄悄換版本 —— 這個 repo 已經踩過這個坑。等 image 由 CI 建置之後改釘 digest。
3. **沒有 `securityContext`。** image 以 root 執行，pod spec 也什麼都沒設
   （`runAsNonRoot`、`readOnlyRootFilesystem`、drop capabilities）。
4. **`automountServiceAccountToken`** 只在後台關掉了，MCP server pod 還是會掛
   default token。
5. **MCP token 走在 URL path 上**，nginx 會把完整 request line 寫進 log，能讀 proxy
   log 的人就拿得到 token。
6. **komibright 的 `ODOO_MCP_ALLOW_UNKNOWN_METHODS=1`** 讓副作用閘門比
   `mcp-odoo-policy` 更寬。要不要收緊是租戶的決定，不是 chart 的預設值。
