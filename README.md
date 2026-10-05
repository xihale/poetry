# 白卷 · 我的诗单

一个诗单的艺术站点。打开抽一首，满屏一首；下滑就是下一首。
可以按时代、作者、体裁、情绪、视角、篇幅六个维度挑着读。

没有首页，没有目录，没有导航栏。屏幕上只有诗，和角落里三个淡到几乎看不见的字。

## 内容

35 首，出自 [古文岛](https://www.guwendao.net)（原古诗文网）的个人收藏。
由 `scripts/fetch-poemlist.py` 导出，再经 `scripts/build-corpus.py` 归类。

先秦到近现代都有，因为**时代取自作者，不取自任何一本选本**：
洛神赋是魏晋，圆圆曲是明，滕王阁序是唐，死水是近现代。

| 时代 | 首 | 体裁 | 首 |
| --- | --- | --- | --- |
| 唐 | 12 | 七言 | 13 |
| 宋 | 12 | 五言 | 11 |
| 明 | 5 | 词 | 4 |
| 近现代 | 3 | 文 | 3 |
| 魏晋 / 金 / 元 | 各 1 | 赋 | 2 |
| | | 杂言 / 现代 | 各 1 |

## 导出诗单

收藏列表是唯一需要登录的页面；诗本身都是公开的，所以 cookie 只发给列表接口。

```bash
# 1. 在浏览器登录后，从开发者工具复制 gsw2017user 的值
export GUWENDAO_COOKIE='<account-id>|<token>|2000/1/1|2000/1/1'
# 或者把 Netscape 格式的 cookie 文件传给 --cookie-jar

# 2. 导出
python3 scripts/fetch-poemlist.py --cookie-jar /tmp/jar.txt
```

结果写到 `.cache/guwendao/poemlist.json`，已 gitignore。新增收藏后重跑即可；
已经抓过的诗会走缓存，只有新诗会再请求。

Cookie 是账号凭证，别提交进仓库。脚本也不会把凭证写进任何产物。

## 六个维度怎么来的

全部读自诗文本身，没有一个来自容器：

- **时代** 取诗文页的〔唐代〕这类标记，也就是作者所属朝代。
- **体裁** 读标题与句读长度：词牌在表内即为词；单行超过 60 字且标题以「赋」结尾
  为赋，否则为文；句长 75% 以上落在 7/5/4 字即七言/五言/四言；近现代的不规则体为现代。
- **情绪**、**视角** 是词表命中：收「愁」是因为诗里真的有愁/泪/断肠，
  收「你」是因为有劝君/思君这类第二人称短语（「君子」不算）。每一条都能在屏幕上核对。
- **篇幅** 按中日韩字数分短/中/长。

## 开发

```bash
bun install
bun run dev          # http://localhost:3000
```

重新生成语料与字体（产物都已提交，只有改源数据时才需要）：

```bash
bun run corpus       # .cache/guwendao/poemlist.json -> public/corpus.json
bun run fonts        # 按语料重新子集化 -> public/fonts/song.woff2
```

`scripts/build-fonts.py` 需要系统里的 Noto Serif CJK SC Light；
若语料里出现扩展 B 区生僻字，它会再生成一个 `rare.woff2` 伴随字体，
没有生僻字时则删除该文件，不白下载。

## 构建与部署

```bash
bun run generate     # 静态站输出到 .output/public
```

推到 `main` 后 GitHub Actions 构建并发布到 GitHub Pages。
项目页在子路径下，工作流通过 `NUXT_APP_BASE_URL` 传入，`nuxt.config.ts` 里的
`baseURL` 与 favicon 路径都跟着它走。

## 结构

```
app/
  pages/index.vue            满屏一首的阅读流；抽签、筛选、滚入下一首
  components/PoemLeaf.vue    一屏诗；进入视口时升起
  components/Facets.vue      六个维度的分类面板，计数联动
  composables/usePoems.ts    长诗分片（赋与文先按句读断行）
  types/poem.ts              语料形状与六个维度
  assets/css/main.css        全部样式：一个字面、一个字重、两种墨
scripts/
  fetch-poemlist.py          从古文岛导出个人收藏
  build-corpus.py            归类：时代 / 体裁 / 情绪 / 视角 / 篇幅
  build-fonts.py             子集化自托管字体
```

设计说明、评审记录与截图证据在 `.design/` 下。
