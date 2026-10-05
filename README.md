# 诗存

xihale 的个人诗稿合集。中文为主，中英混排。

## 设计

方向「简 · 谱」：像翻一册自印的诗集目录，纸、字、线三样东西，把全部诗稿按时间码成一页可扫的谱。

- **字**：题名用楷体（霞鹜文楷），正文用宋体（Noto Serif SC）。两者都是自托管的 woff2 子集。
- **色**：纸 `#F7F5F0`、墨 `#14110E`、朱红 `#A33A2B`。朱红只用在编号和强调，占画面不到一成。
- **线**：两种粗细。主分割线分版面，细线分条目。留白已经分开的地方不再画线。
- **动效**：出场、按下反馈、页面过渡三处，都是同一种「从下方浮上来」的手感。尊重 `prefers-reduced-motion`。

字体子集、候选方向、截图和评审记录都在 `.design/round-01/`。

## 内容

诗稿放在 `content/poems/`，文件名是编号，按编号倒序排列（编号大的更新）。

```
content/poems/12.txt
```

文件格式：第一行是元信息，`标题|附注`，附注通常是日期或作者，可以留空；空一行之后是正文。正文里的空行会被当作诗节间隔保留。

```
死与生|4.18

有的人活着，
他或将继续苟活；
```

新增诗稿后重新构建即可，路由与索引会自动更新。若新诗用到了字体子集之外的生僻字，重跑一次 `bun run fonts`（需要 Python 3 与 fontTools，会读取本机的霞鹜文楷与 Noto Serif CJK）。

`content/draft/` 是不发布的草稿。

## 开发

```bash
bun install
bun run dev        # 开发服务器
bun run generate   # 静态构建，输出到 .output/public
bun run fonts      # 重新生成字体子集
```

站点是纯静态的（Nuxt SSG）。每个诗稿在构建时预渲染成独立页面。

## 部署

推送到 `main` 后由 GitHub Actions 构建并发布到 GitHub Pages，见 `.github/workflows/deploy.yml`。

仓库作为项目站点发布在 `https://<user>.github.io/poetry/`，构建时通过 `NUXT_APP_BASE_URL` 注入这个子路径。绑定自定义域名或改为用户站点（发布在根路径）时，把该环境变量留空即可。
