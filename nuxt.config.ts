const baseURL = process.env.NUXT_APP_BASE_URL || '/'

export default defineNuxtConfig({
  compatibilityDate: '2026-10-05',
  devtools: { enabled: false },

  css: ['~/assets/css/main.css'],

  app: {
    // 部署在子路径时用 NUXT_APP_BASE_URL 传入（如 GitHub Pages 项目页）；根路径不设。
    baseURL: baseURL,
    pageTransition: false,
    head: {
      htmlAttrs: { lang: 'zh-CN' },
      // joined by hand so the path follows baseURL on a project subpath
      link: [
        { rel: 'icon', type: 'image/png', href: `${baseURL}favicon.png` },
      ],
      meta: [{ name: 'theme-color', content: '#faf9f6' }],
    },
  },

  // Static hosting (GitHub Pages): no server at runtime.
  ssr: true,
  nitro: {
    preset: 'github_pages',
  },
})
