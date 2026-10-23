"use client";

import { use, useEffect, useRef, useState } from "react";
import "maplibre-gl/dist/maplibre-gl.css";

type Point = { id: number; libelle: string; critique: boolean; ok: boolean; commentaire: string };
type Detail = {
  plaque: string; conducteur: string; created_at: string; defaut_critique: boolean;
  reponses: Point[]; signature: string | null; lat: number | null; lng: number | null; photos: number[];
};

export default function DetailControle({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [d, setD] = useState<Detail | null>(null);
  const [erreur, setErreur] = useState("");
  const carte = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`/api/admin/controles/${id}`).then(async (r) => {
      if (r.status === 401) return (window.location.href = "/connexion");
      if (!r.ok) return setErreur("Contrôle introuvable.");
      setD(await r.json());
    });
  }, [id]);

  useEffect(() => {
    if (!d || d.lat === null || d.lng === null || !carte.current) return;
    let map: { remove: () => void } | undefined;
    import("maplibre-gl").then(({ default: maplibregl }) => {
      const m = new maplibregl.Map({
        container: carte.current!,
        center: [d.lng!, d.lat!],
        zoom: 14,
        style: {
          version: 8,
          sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap" } },
          layers: [{ id: "osm", type: "raster", source: "osm" }],
        },
      });
      new maplibregl.Marker().setLngLat([d.lng!, d.lat!]).addTo(m);
      map = m;
    });
    return () => map?.remove();
  }, [d]);

  if (erreur) return <p role="alert">{erreur}</p>;
  if (!d) return <p>Chargement…</p>;

  return (
    <main>
      <a href="/admin/controles">← Contrôles</a>
      <h1>{d.plaque}</h1>
      <p><a href={`/api/admin/controles/${id}/pdf`}>Télécharger le PDF</a></p>
      <p>{d.conducteur} · {new Date(d.created_at).toLocaleString("fr-FR")}{d.defaut_critique && " · défaut critique"}</p>
      <ul>
        {d.reponses.map((r) => (
          <li key={r.id}>
            {r.ok ? "✓" : "✗"} {r.libelle}{r.critique && " (critique)"}{r.commentaire && ` : ${r.commentaire}`}
          </li>
        ))}
      </ul>
      {d.photos.map((p) => (
        <a key={p} href={`/api/admin/photos/${p}`} target="_blank"><img src={`/api/admin/photos/${p}`} alt="Photo du contrôle" width={120} /></a>
      ))}
      {d.signature && <p><img src={d.signature} alt="Signature du conducteur" width={200} /></p>}
      {d.lat !== null && <div ref={carte} style={{ height: 240, marginTop: 12 }} />}
    </main>
  );
}
