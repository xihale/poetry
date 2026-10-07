# Server-side webhook deploy (poetry.xeed.ink, gx)

push → GitHub webhook → g 的 Caddy（`*.xeed.ink` 统一反代）→ gx 的 Caddy
（`@deployhook` → unix socket）→ systemd `Accept=yes` → `webhook.mjs`（HMAC 验签）
→ `deploy.sh`（corpus-check + generate + rsync）。空闲进程数：0。
同一模式：xeed.ink（blog）、zp.xeed.ink、zlg.xeed.ink。

## gx 上的布局（root）

    clone:   /home/poetry-ci/poetry            (https clone，public repo)
    secret:  /home/poetry-ci/.webhook-secret   (0600，与 GitHub hook 共享)
    log:     /home/poetry-ci/deploy.log        (deploy.sh 的 stdout+stderr)
    dest:    /srv/poetry                       (Caddy root，poetry-ci 所有)
    status:  /srv/poetry/deploy-status.json    (webhook.mjs 写)
    meta:    /srv/poetry/deploy-meta.json      (deploy.sh 写，来自构建的树)
    ntfy:    /home/poetry-ci/.ntfy-notify      (0600，共享 topic 的凭据)
    attic:   /home/poetry-ci/poetry-attic      (退役的 /_nuxt /corpus /fonts，7 天)
    lock:    /home/poetry-ci/.deploy.lock      (flock；排队标记 .deploy-rerun)
    units:   /etc/systemd/system/poetry-deploy.socket + poetry-deploy@.service
    socket:  /run/poetry-deploy.sock           (poetry-ci:caddy 0660)
    hook:    https://poetry.xeed.ink/hooks/poetry-deploy (POST，push 事件)

## 缓存契约（gx 的 Caddy 块 ↔ `app/utils/bytes.ts`）

- `/_nuxt/**` 内容哈希文件名 → `max-age=31536000, immutable`；
- `/corpus/**` 文件名不带哈希，应用给每个请求加 `?v=CORPUS_BUILD` → 同样
  `immutable`；语料一换戳一换，URL 全换，老缓存自然作废；
- `/fonts/**` 无哈希 → 7 天 + ETag，与 attic 保留期一致；
- `/`、`200.html`、`404.html`、`_payload.json`、`deploy-*.json` → `no-cache`
  （ETag 304），新部署立刻可见；
- `/corpus/**` 已是 gzip，`encode` 豁免；未知路径回 `404.html`（状态 404）。

## 一次性开通（2026-10-07）

```sh
useradd -u 1506 -m -s /bin/bash poetry-ci && passwd -l poetry-ci
install -d -o poetry-ci -g poetry-ci -m 0755 /srv/poetry
runuser -u poetry-ci -- git clone https://github.com/xihale/poetry /home/poetry-ci/poetry
openssl rand -hex 32 > /home/poetry-ci/.webhook-secret
chown poetry-ci: /home/poetry-ci/.webhook-secret && chmod 600 $_
install -m 600 /home/blog-ci/.ntfy-notify /home/poetry-ci/.ntfy-notify
chown poetry-ci: /home/poetry-ci/.ntfy-notify
# units → /etc/systemd/system/poetry-deploy.{socket,@.service}
systemctl daemon-reload && systemctl enable --now poetry-deploy.socket
```

gx 的 Caddy 块里 hook 的 `reverse_proxy unix//run/poetry-deploy.sock` 包在
`route` 最前——指令顺序会把 `file_server`/错误页放在它前面，不包 route
hook 会被先改写成 404。

## 日常运维

```sh
# 手动种子/重部署
runuser -u poetry-ci -- env HOME=/home/poetry-ci bash ~/poetry/scripts/server/deploy.sh
# 跟一次部署
ssh gx tail -f /home/poetry-ci/deploy.log
# 伪造一次 push（不提交）——本地用共享 secret 签名
SECRET=$(ssh gx cat /home/poetry-ci/.webhook-secret)
PAYLOAD='{"ref":"refs/heads/main","after":"<sha>","deleted":false}'
SIG="sha256=$(printf %s "$PAYLOAD" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $NF}')"
curl -i -X POST https://poetry.xeed.ink/hooks/poetry-deploy \
  -H "content-type: application/json" -H "x-github-event: push" \
  -H "x-hub-signature-256: $SIG" -d "$PAYLOAD"
```

部署先答 GitHub（~10s 期限）再构建；冒烟：错签名 → 403，`ping` 事件 → 200。
其余路径落到站点本身（只有精确的 hook 路径特殊）。

## 可观测

- `https://poetry.xeed.ink/deploy-status.json` — 最近一次 webhook 部署的结果
  （building/success/failure、sha、时间、exitCode）。「部署了吗」看这里。
- `https://poetry.xeed.ink/deploy-meta.json` — 线上到底是什么（deploy.sh 从
  它构建的那棵树里写）。
- 每次结束都有 ntfy 推送（与 blog 同一 topic `webhook-deploy`），标题
  `[poetry@gx] deploy success|failure`。
- `ssh gx tail -f /home/poetry-ci/deploy.log` — 完整构建输出；失败以 `FATAL:`
  结束，上一个好部署不动。
- GitHub 的 webhook deliveries 页只证明送达：接收器先答 200 再构建，构建红了
  那里仍是绿的。

## 语料

`public/corpus/`（14,470 个文件，64 MB）是**提交进 git 的产物**：部署是纯构建，
gx 上不需要 224 MB 的上游镜像。重建语料 = `bun run corpus && bun run search`
后随普通提交发布；attic 保证发布瞬间正在读的会话拿得到旧文件。
