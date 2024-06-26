
import PoemList from '../ui/PoemList'
import './globals.css'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'Poetry',
  description: 'Poetry of xihale',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <head>
        <link rel="icon" href="/favicon.png" />
      </head>
      <body>
        <PoemList></PoemList>
        {children}
      </body>
    </html>
  )
}
