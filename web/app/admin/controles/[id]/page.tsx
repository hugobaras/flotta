"use client";

import Link from "next/link";
import { use, useEffect, useRef, useState } from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import { Coche, dateHeure, Etat, Plaque } from "../../../ui";

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
      new maplibregl.Marker({ color: "#1d3f9e" }).setLngLat([d.lng!, d.lat!]).addTo(m);
      map = m;
    });
    return () => map?.remove();
  }, [d]);

  if (erreur) return <div className="notice danger" role="alert">{erreur}</div>;
  if (!d) return <p className="muted">Chargement…</p>;

  const defauts = d.reponses.filter((r) => !r.ok).length;
  const annexes = d.photos.length > 0 || d.signature || d.lat !== null;

  return (
    <>
      <p style={{ marginBottom: 20 }}><Link href="/admin/controles">Retour aux contrôles</Link></p>
      <div className="detail-head">
        <Plaque size="xl">{d.plaque}</Plaque>
        {d.defaut_critique ? <Etat statut="bloque" label="Défaut critique" />
          : defauts ? <Etat statut="defaut" label="Défaut" /> : <Etat statut="controle" label="Conforme" />}
      </div>
      <div className="page-head">
        <p className="detail-meta" style={{ margin: 0 }}>{d.conducteur} · {dateHeure(d.created_at)}</p>
        <a className="btn" href={`/api/admin/controles/${id}/pdf`}>Télécharger le PDF</a>
      </div>

      <div className={annexes ? "detail-grid" : undefined}>
        <section className="section" style={{ marginTop: 12 }} aria-labelledby="points">
          <h2 id="points">Points contrôlés <small>{defauts ? `${defauts} défaut${defauts > 1 ? "s" : ""}` : "Aucun défaut"}</small></h2>
          <ul className="checks">
            {d.reponses.map((r) => (
              <li key={r.id} className={r.ok ? "ok" : "ko"}>
                <Coche ok={r.ok} />
                <span className="label-point">
                  {r.libelle}
                  {r.commentaire && <span className="note">{r.commentaire}</span>}
                </span>
                {r.critique && <span className="critique">Critique</span>}
              </li>
            ))}
          </ul>
        </section>

        {annexes && (
          <div>
            {d.photos.length > 0 && (
              <section className="section" style={{ marginTop: 12 }} aria-labelledby="photos">
                <h2 id="photos">Photos</h2>
                <div className="photo-grid">
                  {d.photos.map((p) => (
                    <a key={p} href={`/api/admin/photos/${p}`} target="_blank" rel="noreferrer"><img src={`/api/admin/photos/${p}`} alt="Photo jointe au contrôle" /></a>
                  ))}
                </div>
              </section>
            )}
            {d.signature && (
              <section className="section" style={{ marginTop: d.photos.length ? 28 : 12 }} aria-labelledby="sig">
                <h2 id="sig">Signature</h2>
                <div className="sig-box"><img src={d.signature} alt="Signature du conducteur" /></div>
              </section>
            )}
            {d.lat !== null && (
              <section className="section" style={{ marginTop: d.photos.length || d.signature ? 28 : 12 }} aria-labelledby="pos">
                <h2 id="pos">Position <small className="num">{d.lat.toFixed(4)}, {d.lng!.toFixed(4)}</small></h2>
                <div ref={carte} className="map" />
              </section>
            )}
          </div>
        )}
      </div>
    </>
  );
}
