import type { Metadata } from 'next';
import { Plus_Jakarta_Sans, Instrument_Sans, JetBrains_Mono } from 'next/font/google';
import { Toaster } from 'sonner';
import './globals.css';

const display = Plus_Jakarta_Sans({
  variable: '--font-display',
  subsets: ['latin'],
  weight: ['500', '600', '700'],
});

const body = Instrument_Sans({
  variable: '--font-body',
  subsets: ['latin'],
  weight: ['400', '500'],
});

const mono = JetBrains_Mono({
  variable: '--font-mono',
  subsets: ['latin'],
  weight: ['400'],
});

export const metadata: Metadata = {
  title: 'QA-Genius — The QA workspace that shows its evidence',
  description:
    'AI workspace for QA engineers: turn stories, bug notes, and requirements into structured, reviewable QA artifacts.',
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${display.variable} ${body.variable} ${mono.variable} antialiased`}>
        {children}
        <Toaster richColors={false} />
      </body>
    </html>
  );
}
