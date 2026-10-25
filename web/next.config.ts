import type { NextConfig } from "next";

const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [{ source: "/:path*", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(self)" },
    ] }];
  },
  async redirects() {
    // Anciennes pages : les sections vivent maintenant dans Configuration, Planning ou Aujourd'hui.
    return [
      ...["flotte", "conducteurs", "depots", "checklists", "parametres", "integrations", "offre", "demarrer"].map((id) => ({ source: `/admin/${id}`, destination: `/admin/configuration#${id}`, permanent: false })),
      { source: "/admin/commandes", destination: "/admin/planning#commandes", permanent: false },
      { source: "/admin/itineraires", destination: "/admin/planning#itineraire", permanent: false },
      { source: "/admin/controles", destination: "/admin#controles", permanent: false },
    ];
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${process.env.API_URL ?? "http://localhost:8000"}/api/:path*` }];
  },
};

export default config;
