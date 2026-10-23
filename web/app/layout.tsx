export const metadata = { title: "Transport", description: "Contrôle avant départ" };

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="fr">
      <body style={{ fontFamily: "system-ui", margin: 0, padding: 16, maxWidth: 560 }}>{children}</body>
    </html>
  );
}
