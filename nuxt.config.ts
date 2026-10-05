const baseURL = process.env.NUXT_APP_BASE_URL || '/'

export default defineNuxtConfig({
  compatibilityDate: '2026-10-05',
  devtools: { enabled: false },

  css: ['~/assets/css/main.css'],

  app: {
    // GitHub Pages project site lives under /<repo>/; the deploy workflow sets this.
    baseURL: baseURL,
    pageTransition: { name: 'page', mode: 'out-in' },
    head: {
      htmlAttrs: { lang: 'zh-CN' },
      // joined by hand so the path follows baseURL on a project subpath
      link: [
        { rel: 'icon', type: 'image/png', href: `${baseURL}favicon.png` },
      ],
      meta: [{ name: 'theme-color', content: '#f7f5f0' }],
    },
  },

  // Static hosting (GitHub Pages): no server at runtime.
  ssr: true,
  nitro: {
    preset: 'github_pages',
  },
})
