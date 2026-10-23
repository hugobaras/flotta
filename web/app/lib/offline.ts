// File d'attente des contrôles faits sans réseau : IndexedDB (les photos sont trop lourdes pour localStorage).
// Chaque envoi porte un client_id : le rejouer côté serveur ne crée jamais de doublon.

export type Envoi = { client_id: string; token: string; payload: Record<string, unknown>; photos: Blob[]; cree: number; type?: "controle" | "livraison" };

const BASE = "flotta";
const STORE = "envois";

function ouvrir(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(BASE, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(STORE, { keyPath: "client_id" });
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function tx<T>(mode: IDBTransactionMode, fn: (s: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const db = await ouvrir();
  return new Promise((resolve, reject) => {
    const r = fn(db.transaction(STORE, mode).objectStore(STORE));
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

export const mettreEnFile = (e: Envoi) => tx("readwrite", (s) => s.put(e));
export const retirer = (id: string) => tx("readwrite", (s) => s.delete(id));
export const enAttente = () => tx<Envoi[]>("readonly", (s) => s.getAll() as IDBRequest<Envoi[]>);

/** Erreurs qui justifient de garder l'envoi pour plus tard (réseau, serveur indisponible). */
export const transitoire = (e: unknown, statut?: number) => e instanceof TypeError || (statut !== undefined && [502, 503, 504].includes(statut));

/** Envoie un contrôle puis ses photos. Renvoie la réponse du serveur ou lève en cas d'échec transitoire. */
export async function envoyerUn(e: Envoi): Promise<{ id: number; bloque: boolean; photosManquantes: number }> {
  const livraison = e.type === "livraison";
  const r = await fetch(livraison ? `/api/tournee/${e.token}/evenements` : `/api/controle/${e.token}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...e.payload, client_id: e.client_id }) });
  if (!r.ok) throw Object.assign(new Error("refusé"), { statut: r.status });
  const j = await r.json();
  let manque = 0;
  for (const f of e.photos) {
    const form = new FormData();
    form.append("photo", f);
    try {
      if (!(await fetch(livraison ? `/api/tournee/${e.token}/evenements/${j.id}/photos` : `/api/controle/${e.token}/${j.id}/photos`, { method: "POST", body: form })).ok) manque++;
    } catch {
      manque++;
    }
  }
  return { id: j.id, bloque: !!j.bloque, photosManquantes: manque };
}

/** Vide la file dans l'ordre. S'arrête au premier échec transitoire ; abandonne les envois refusés pour de bon (4xx). */
export async function viderLaFile(): Promise<{ envoyes: number; restants: number }> {
  let envoyes = 0;
  for (const e of (await enAttente()).sort((a, b) => a.cree - b.cree)) {
    try {
      await envoyerUn(e);
      await retirer(e.client_id);
      envoyes++;
    } catch (err) {
      const statut = (err as { statut?: number }).statut;
      if (statut && statut >= 400 && statut < 500 && statut !== 429) await retirer(e.client_id); // ex. badge expiré : inutile de réessayer
      else break;
    }
  }
  return { envoyes, restants: (await enAttente()).length };
}
