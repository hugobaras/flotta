"use client";

import { useEffect, useRef } from "react";
import "maplibre-gl/dist/maplibre-gl.css";

export type Point = { id: number; lat: number; lng: number; couleur: string; titre: string; selectionne?: boolean };

const chargerLib = () => import("maplibre-gl");
type Lib = Awaited<ReturnType<typeof chargerLib>>["default"];

const STYLE = {
  version: 8 as const,
  sources: { osm: { type: "raster" as const, tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap" } },
  layers: [{ id: "osm", type: "raster" as const, source: "osm" }],
};

/** Carte MapLibre : marqueurs colorés, clic sur un marqueur ou sur la carte (pour placer une adresse à la main). */
export default function Carte({ points, onPoint, onCarte, curseur, hauteur = 420 }: {
  points: Point[]; onPoint?: (id: number) => void; onCarte?: (lat: number, lng: number) => void; curseur?: boolean; hauteur?: number;
}) {
  const conteneur = useRef<HTMLDivElement>(null);
  const carte = useRef<import("maplibre-gl").Map | null>(null);
  const marqueurs = useRef<import("maplibre-gl").Marker[]>([]);
  const rappels = useRef({ onPoint, onCarte });
  rappels.current = { onPoint, onCarte };

  useEffect(() => {
    let vivant = true;
    import("maplibre-gl").then(({ default: maplibregl }) => {
      if (!vivant || !conteneur.current || carte.current) return;
      const m = new maplibregl.Map({ container: conteneur.current, style: STYLE, center: [2.35, 46.8], zoom: 4.6 });
      m.on("click", (e) => rappels.current.onCarte?.(e.lngLat.lat, e.lngLat.lng));
      carte.current = m;
      dessiner(maplibregl);
    });
    return () => {
      vivant = false;
      carte.current?.remove();
      carte.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function dessiner(lib?: Lib) {
    const maplibregl = lib ?? (await import("maplibre-gl")).default;
    const m = carte.current;
    if (!m) return;
    marqueurs.current.forEach((x) => x.remove());
    marqueurs.current = points.map((p) => {
      const el = document.createElement("button");
      el.type = "button";
      el.title = p.titre;
      el.setAttribute("aria-label", p.titre);
      el.style.cssText = `width:${p.selectionne ? 22 : 14}px;height:${p.selectionne ? 22 : 14}px;border-radius:50%;background:${p.couleur};border:2px solid #fff;box-shadow:0 0 0 1px #111418;cursor:pointer;padding:0`;
      el.addEventListener("click", (ev) => { ev.stopPropagation(); rappels.current.onPoint?.(p.id); });
      return new maplibregl.Marker({ element: el }).setLngLat([p.lng, p.lat]).addTo(m);
    });
    if (points.length) {
      const b = new maplibregl.LngLatBounds();
      points.forEach((p) => b.extend([p.lng, p.lat]));
      m.fitBounds(b, { padding: 50, maxZoom: 13, duration: 0 });
    }
  }

  useEffect(() => {
    dessiner();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [points]);

  useEffect(() => {
    carte.current?.getCanvas && (carte.current.getCanvas().style.cursor = curseur ? "crosshair" : "");
  }, [curseur]);

  return <div ref={conteneur} className="map" style={{ height: hauteur, marginTop: 0 }} />;
}
