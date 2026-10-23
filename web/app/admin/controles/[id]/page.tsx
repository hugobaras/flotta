"use client";

import { ArrowLeft, Check, Download, TriangleAlert, X } from "lucide-react";
import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import { dateHeure, Plaque } from "../../../ui";

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
      if (!r.ok) return setErreur("Ce contrôle est introuvable.");
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
      new maplibregl.Marker({ color: "#4054d6" }).setLngLat([d.lng!, d.lat!]).addTo(m);
      map = m;
    });
    return () => map?.remove();
  }, [d]);

  if (erreur) return <div className="alert alert-danger" role="alert"><TriangleAlert aria-hidden /><span>{erreur}</span></div>;
  if (!d) return <p className="muted">Chargement…</p>;

  const defauts = d.reponses.filter((r) => !r.ok).length;
  const annexes = d.photos.length > 0 || d.signature || d.lat !== null;

  return (
    <>
      <Link className="btn btn-ghost btn-sm" href="/admin/controles" style={{ marginBottom: 12, marginLeft: -10 }}><ArrowLeft aria-hidden />Contrôles</Link>
      <div className="page-header">
        <div>
          <h1 style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <Plaque>{d.plaque}</Plaque>
            {d.defaut_critique ? <span className="badge badge-danger">Défaut critique</span>
              : defauts ? <span className="badge badge-warn">Défaut</span> : <span className="badge badge-ok">Conforme</span>}
          </h1>
          <p>{d.conducteur} · {dateHeure(d.created_at)}</p>
        </div>
        <a className="btn" href={`/api/admin/controles/${id}/pdf`}><Download aria-hidden />Télécharger le PDF</a>
      </div>

      <div className={annexes ? "detail-grid" : "stack"}>
        <section className="panel" aria-labelledby="points">
          <div className="panel-head"><h2 id="points">Points contrôlés</h2><span className="muted">{defauts ? `${defauts} défaut${defauts > 1 ? "s" : ""}` : "Aucun défaut"}</span></div>
          <ul className="checks">
            {d.reponses.map((r) => (
              <li key={r.id} className={r.ok ? "ok" : "ko"}>
                {r.ok ? <Check aria-label="Conforme" /> : <X aria-label="Défaut" />}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontWeight: 550 }}>{r.libelle}</div>
                  {r.commentaire && <div className="note">{r.commentaire}</div>}
                </div>
                {r.critique && <span className="badge">Critique</span>}
              </li>
            ))}
          </ul>
        </section>

        <div className="stack">
          {d.photos.length > 0 && (
            <section className="panel" aria-labelledby="photos">
              <div className="panel-head"><h2 id="photos">Photos</h2></div>
              <div className="panel-body photo-grid">
                {d.photos.map((p) => (
                  <a key={p} href={`/api/admin/photos/${p}`} target="_blank" rel="noreferrer"><img src={`/api/admin/photos/${p}`} alt="Photo jointe au contrôle" /></a>
                ))}
              </div>
            </section>
          )}
          {d.signature && (
            <section className="panel" aria-labelledby="sig">
              <div className="panel-head"><h2 id="sig">Signature</h2></div>
              <div className="panel-body"><div className="sig-box"><img src={d.signature} alt="Signature du conducteur" /></div></div>
            </section>
          )}
          {d.lat !== null && (
            <section className="panel" aria-labelledby="pos">
              <div className="panel-head"><h2 id="pos">Position</h2><span className="muted num">{d.lat.toFixed(4)}, {d.lng!.toFixed(4)}</span></div>
              <div className="panel-body"><div ref={carte} className="map" /></div>
            </section>
          )}
        </div>
      </div>
    </>
  );
}
