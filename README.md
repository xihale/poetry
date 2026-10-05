# 白卷 · 中国古典诗选

一个中国古典诗选的艺术站点。打开抽一首，满屏一首；下滑就是下一首。
可以按诗集、时代、诗人、体裁、情绪、视角、篇幅七个维度挑着读。

没有首页，没有目录，没有导航栏。屏幕上只有诗，和角落里三个淡到几乎看不见的字。

## 内容

1,298 首，六部经典，先秦到清，180 位诗人：

| 集 | 首数 | 时代 |
| --- | --- | --- |
| 诗经 | 305 | 先秦 |
| 楚辞 | 65 | 先秦 |
| 曹操诗集 | 26 | 汉 |
| 唐诗三百首 | 364 | 唐 |
| 宋词三百首 | 280 | 宋 |
| 纳兰词 | 258 | 清 |

数据取自 [chinese-poetry](https://github.com/chinese-poetry/chinese-poetry)（MIT），
繁体统一转简体。取成集的选本而非全唐诗全宋词：选本本身经过时间筛过，
而且一千三百首能整包发给浏览器，不必后端分页。

## 开发

```bash
bun install
bun run dev          # http://localhost:3000
```

重新生成语料与字体（语料和字体产物都已提交，只有改动源数据时才需要）：

```bash
bun run corpus       # 抓取并规范化六部选本 -> public/corpus.json
bun run fonts        # 按语料重新子集化 -> public/fonts/*.woff2
```

`scripts/build-corpus.py` 需要 `opencc`（繁简转换）与 `fontTools`；
`scripts/build-fonts.py` 需要系统里的 Noto Serif CJK SC Light 与霞鹜文楷。

## 构建与部署

```bash
bun run generate     # 静态站输出到 .output/public
```

推到 `main` 后 GitHub Actions 会构建并发布到 GitHub Pages。
项目页在子路径下，工作流通过 `NUXT_APP_BASE_URL` 传入，`nuxt.config.ts` 里的
`baseURL` 与 favicon 路径都跟着它走。

## 结构

```
app/
  pages/index.vue            满屏一首的阅读流；抽签、筛选、滚入下一首
  components/PoemLeaf.vue    一屏诗；进入视口时升起
  components/Facets.vue      七个维度的分类面板，计数联动
  composables/usePoems.ts    长诗分片
  types/poem.ts              语料形状与七个维度
  assets/css/main.css        全部样式：一个字面、一个字重、两种墨
scripts/
  build-corpus.py            抓取 + 规范化 + 字面标注
  build-fonts.py             子集化自托管字体
```

设计说明、方向探索、评审记录与截图证据在 `.design/` 下。
