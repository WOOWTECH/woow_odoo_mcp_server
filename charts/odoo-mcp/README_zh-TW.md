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
  -f deploy/woow-k3s/<tenant>.yaml
```

不 clone，直接用 GitHub tarball。chart 放在子目錄，所以要先解開：
`helm install <url>` 只吃 `Chart.yaml` 在壓縮檔根目錄的 chart，而 GitHub 的
原始碼壓縮檔根目錄永遠不是 chart：

```bash
REF=main   # 任何 branch 或 tag
curl -fsSL "https://github.com/WOOWTECH/woow_odoo_mcp_server/archive/refs/heads/${REF}.tar.gz" | tar -xz
# GitHub 會用 ref 當解開後的目錄名，並把 / 換成 -
SRC="woow_odoo_mcp_server-${REF//\//-}"   # 解開後的 repo 目錄

helm install mcp-odoo "$SRC/charts/odoo-mcp" -n <tenant> \
  -f "$SRC/deploy/woow-k3s/<tenant>.yaml"
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
| `nodeSelector` | `{}` | 所有 Pod（含 `helm test` Pod）的節點選擇；留空時不會在正式 Pod template 上加任何欄位 |
| `tests.timeoutSeconds` | `180` | smoke Pod 重試連線的上限秒數 |

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

## 不用 private image 也能測

`image.repository`（`ghcr.io/woowtech/woow-odoo-mcp-server`）是一個 **private**
的 GHCR package，預設用 `imagePullSecrets: [{name: mcp-admin-ghcr}]` 拉取，而這
個 Secret 只存在於正式 tenant 的 namespace 裡——是每個 tenant 手動建一次的，跟這
個 chart 無關。**不要把某個 tenant 的 `mcp-admin-ghcr`（或任何其他正式環境的
pull secret）複製進測試 namespace**；Helm 遷移 phase 1 的規則只允許在測試裡重用
一個真實的組織憑證（OpenRouter key，用在遷移計畫裡另一個功能測試），GHCR pull
secret 不算在內。

真正跑得起 image、也是這份 chart 在 `woow-k3s` 上驗證時採用的做法：

* **把 Pod 釘在已經快取這個 image 的節點上。** 現在跑著租戶 MCP 的節點，
  containerd 裡本來就有 `ghcr.io/woowtech/woow-odoo-mcp-server`；只要
  `image.pullPolicy=IfNotPresent` 加上 `imagePullSecrets: []`，kubelet 完全不會
  連 ghcr.io，也就不需要任何憑證：

  ```bash
  # 找一個今天就在跑 MCP pod 的節點
  NODE=$(kubectl get pods -A -o jsonpath='{range .items[*]}{.spec.nodeName}{"\t"}{.spec.containers[0].image}{"\n"}{end}' \
         | grep woow-odoo-mcp-server | head -1 | cut -f1)

  helm install mcp-odoo charts/odoo-mcp -n ht-odoo-mcp --create-namespace \
    --set imagePullSecrets=null --set image.pullPolicy=IfNotPresent \
    --set nodeSelector."kubernetes\.io/hostname"="$NODE" \
    --set storageClassName=longhorn-delete \
    --set odoo.url=http://odoo-stub.ht-odoo-mcp.svc.cluster.local:8069 \
    --set odoo.db=testdb \
    --set "server.allowedHosts={localhost,127.0.0.1,mcp-odoo.ht-odoo-mcp.svc.cluster.local,mcp-odoo-proxy.ht-odoo-mcp.svc.cluster.local}" \
    --set secrets.create=true --set secrets.odooPassword="$(openssl rand -hex 16)" \
    --set proxy.config.create=true --set proxy.config.authToken="$(openssl rand -hex 10)"

  helm test mcp-odoo -n ht-odoo-mcp --logs
  ```

  所有 instance values 都沒有設 `nodeSelector`，所以它不會在正式 Pod template 上
  加任何欄位。

  `odoo.url` 請指向同一個測試 namespace 裡的 stub，不要指向真的租戶：MCP server
  是延遲連線 Odoo 的，只要 stub 會回 `/xmlrpc/2/*` 跟 `/jsonrpc`，
  `initialize` 和 `tools/list` 就能通。

* **App 本身的行為，在叢集外驗證** — 在虛擬環境裡裝 Dockerfile 裝的同一個
  `odoo-mcp` 版本，套用 `files/patches/*.py`（不修改），直接跑
  `python3 -m odoo_mcp --transport streamable-http …`；另外用 `uvicorn` 跑
  `odoo_mcp_admin`，打 `/healthz`。完全不需要叢集。

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
  -f deploy/woow-k3s/<tenant>.yaml --take-ownership
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
7. **`persistence.enabled: true` 時重新 roll server pod 會卡住。** `/data` 是
   ReadWriteOnce，而 Deployment 沿用正式環境的 `RollingUpdate`：新 pod 會先被建出來，
   舊 pod 才會消失。若排到別的節點，新 pod 就會停在
   `Multi-Attach error for volume …`，直到舊 pod 消失為止（在 woow-k3s 的測試安裝中
   實際遇到；正式環境 `kubectl rollout restart` 之所以沒事，是因為新 pod 剛好排在同一個
   節點）。改成 `strategy: Recreate` 可以解決，但那會動到正式的 Deployment spec，所以不放
   進這版 chart。在那之前，這種租戶請用 `kubectl scale deploy/mcp-odoo --replicas=0`
   再調回 1 的方式重啟。
8. **MCP server 沒有 readiness probe。** 正式環境的 Deployment 本來就沒有，所以
   chart 也不加：`kubectl rollout status` 會在 uvicorn 還沒起來前就返回，Service
   也會在連接埠還沒開之前就有 endpoint。`helm test` 的 smoke pod 用重試
   （`tests.timeoutSeconds`）繞過這點。加上 probe 會改到正式的 Pod template。
