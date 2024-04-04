/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  swcMinify: true,

  output: 'export',
  distDir: 'build',
}

module.exports = nextConfig
