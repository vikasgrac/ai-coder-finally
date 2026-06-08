import "./globals.css";

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <head>
        <title>FinAlly — AI Trading Workstation</title>
        <meta name="description" content="AI-powered Indian stock market trading workstation" />
        <link
          href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@300;400;500;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap"
          rel="stylesheet"
        />
      </head>
      <body style={{ background: "#0d1117", color: "#c9d1d9", margin: 0, padding: 0 }}>
        {children}
      </body>
    </html>
  );
}
