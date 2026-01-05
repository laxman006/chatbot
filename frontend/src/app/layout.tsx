import type { Metadata } from 'next';
import './globals.css';
import Script from 'next/script';

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_BASE_URL || 'https://ai.cloudfuze.com'),
  title: 'CloudFuze AI Assistant - Smart Cloud Migration Assistant',
  description: 'Ask CloudFuze AI Assistant for migration-related queries and get instant, intelligent responses. Simplify cloud data migration with AI-powered assistance.',
  keywords: 'AI Chat Agent, AI assistant, cloud migration chatbot, CloudFuze AI, migrate data with AI',
  authors: [{ name: 'CloudFuze, Inc' }],
  robots: 'noindex, follow',
  icons: {
    icon: '/images/CloudFuze-icon-64x64.png',
  },
  verification: {
    google: 'PhjlsaI1LwJ0elVNYMvimmGx_a_PXGb6XQZZSRWsm10',
  },
  openGraph: {
    title: 'CloudFuze AI Assistant',
    description: 'CloudFuze AI Assistant simplifies cloud migration by providing real-time AI-powered assistance, expert insights, and seamless solutions for businesses of all sizes.',
    url: 'https://ai.cloudfuze.com',
    siteName: 'CloudFuze AI Assistant',
    images: [
      {
        url: '/CloudFuze-AI-og-Image.png',
        width: 1200,
        height: 630,
      }
    ],
    type: 'website',
  },
  twitter: {
    card: 'summary_large_image',
    title: 'CloudFuze AI Assistant',
    description: 'CloudFuze AI Assistant offers instant, AI-driven guidance for cloud migration. Get expert insights and solutions tailored for your business.',
    images: ['/CloudFuze-AI-og-Image.png'],
  },
  alternates: {
    canonical: 'https://ai.cloudfuze.com',
  },
  other: {
    'article:published_time': '2025-03-18T00:00:00Z',
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        {/* Google Tag Manager */}
        <Script id="gtm-script" strategy="afterInteractive">
          {`
            (function(w,d,s,l,i){
              w[l]=w[l]||[];
              w[l].push({'gtm.start': new Date().getTime(),event:'gtm.js'});
              var f=d.getElementsByTagName(s)[0],
                  j=d.createElement(s),
                  dl=l!='dataLayer'?'&l='+l:'';
              j.async=true;
              j.src='https://www.googletagmanager.com/gtm.js?id='+i+dl;
              f.parentNode.insertBefore(j,f);
            })(window,document,'script','dataLayer','GTM-K7XGC7N3');
          `}
        </Script>
        
        {/* Structured Data */}
        <Script id="structured-data" type="application/ld+json">
          {`
            {
              "@context": "https://schema.org",
              "@type": "SoftwareApplication",
              "name": "CloudFuze AI Assistant",
              "description": "CloudFuze AI Assistant offers instant, AI-driven guidance for cloud migration. Get expert insights and solutions tailored for your business.",
              "applicationCategory": "BusinessApplication",
              "operatingSystem": "Web",
              "url": "https://ai.cloudfuze.com",
              "image": "/CloudFuze-AI-og-Image.png",
              "datePublished": "2025-03-20",
              "dateModified": "2025-03-19",
              "publisher": {
                "@type": "Organization",
                "name": "CloudFuze",
                "url": "https://www.cloudfuze.com"
              },
              "offers": {
                "@type": "Offer",
                "price": "0",
                "priceCurrency": "USD"
              }
            }
          `}
        </Script>
        
        {/* Marked.js for Markdown rendering */}
        <Script 
          src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"
          strategy="beforeInteractive"
        />
        
      </head>
      <body>
        {/* Google Tag Manager (noscript) */}
        <noscript>
          <iframe 
            src="https://www.googletagmanager.com/ns.html?id=GTM-K7XGC7N3"
            height="0" 
            width="0" 
            style={{display: 'none', visibility: 'hidden'}}
          />
        </noscript>
        
        {children}
      </body>
    </html>
  );
}
