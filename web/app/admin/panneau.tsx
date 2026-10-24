"use client";

import { useEffect, useRef, useState } from "react";

// Section repliable ; le contenu (et ses requêtes) n'est monté qu'à la première ouverture.
export function Panneau({ id, titre, defaut = false, groupe, etat, children }: { id: string; titre: string; defaut?: boolean; groupe?: string; etat?: string; children: React.ReactNode }) {
  const [ouvert, setOuvert] = useState(defaut);
  const [monte, setMonte] = useState(defaut);
  const ref = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    if (window.location.hash === `#${id}`) {
      setOuvert(true);
      setMonte(true);
      setTimeout(() => ref.current?.scrollIntoView({ block: "start" }), 150);
    }
  }, [id]);

  return (
    <details ref={ref} id={id} name={groupe} className="panneau" open={ouvert} onToggle={(e) => { const o = e.currentTarget.open; setOuvert(o); if (o) setMonte(true); }}>
      <summary><h2>{titre}</h2>{etat && <span className="panneau-etat">{etat}</span>}</summary>
      {monte && <div className="panneau-corps">{children}</div>}
    </details>
  );
}
