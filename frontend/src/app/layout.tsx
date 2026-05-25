import type { Metadata } from 'next';
import { Outfit, Figtree } from 'next/font/google';
import './globals.css';
import { Toaster } from 'sonner';

const outfit = Outfit({
  subsets: ['latin'],
  variable: '--font-heading',
  display: 'swap',
});

const figtree = Figtree({
  subsets: ['latin'],
  variable: '--font-body',
  display: 'swap',
});

export const metadata: Metadata = {
  title: 'ThreadComb — Every brand deal lives in a thread',
  description:
    'AI-powered creator operations platform. ThreadComb reads your brand deal threads, drafts replies in your voice, and chases overdue invoices — with your approval.',
  icons: {
    icon: '/favicon.svg',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${outfit.variable} ${figtree.variable}`}>
      <body className="min-h-dvh bg-background text-foreground antialiased">
        {children}
        <Toaster richColors closeButton position="top-center" />
      </body>
    </html>
  );
}
