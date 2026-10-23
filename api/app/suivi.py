"""Suivi en direct d'un plan et replanification **proposée** (retard, commande urgente, panne) : rien n'est modifié sans validation."""
from dataclasses import dataclass, field
from datetime import date, datetime, time as heure, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import livraisons, matrices, planning, plans, routage, trafic
from .exploitation import PARIS
from .models import Order, Plan, Vehicle

FINAUX = livraisons.FINAUX


def minutes_du_jour(dt: datetime, jour: date) -> float:
    """Instant -> minutes depuis minuit (heure de Paris) du jour du plan."""
    if dt.tzinfo is None:  # SQLite rend des dates naïves : elles sont en UTC
        dt = dt.replace(tzinfo=timezone.utc)
    return (dt.astimezone(PARIS) - datetime.combine(jour, heure.min, tzinfo=PARIS)).total_seconds() / 60


@dataclass
class Vivant:
    """État réel d'une tournée à l'instant présent : ce qui est fait, ce qui reste, d'où repart le camion."""
    vehicule_id: int
    verrouille: bool
    conducteur_id: int | None
    complet: list[int]  # tous les arrêts de la tournée, dans l'ordre du plan
    restants: list[int]  # arrêts encore à faire
    depuis_ligne: int  # ligne des matrices de la dernière position connue (0 = dépôt)
    depuis_min: float  # heure à laquelle le camion repart de cette position
    chrono: object
    figes: set[int] = field(default_factory=set)  # arrêts verrouillés
    rotations: dict[int, int] = field(default_factory=dict)  # rotation de chaque arrêt de la tournée
    rotation_depuis: int = 1  # rotation en cours à la position actuelle

    def copie(self) -> "Vivant":
        return Vivant(self.vehicule_id, self.verrouille, self.conducteur_id, list(self.complet), list(self.restants), self.depuis_ligne, self.depuis_min,
                      self.chrono, set(self.figes), dict(self.rotations), self.rotation_depuis)

    def rotations_restantes(self) -> list[int]:
        return [self.rotations.get(i, 1) for i in self.restants]

    def retirer(self, order_id: int):
        self.restants.remove(order_id)
        self.complet.remove(order_id)

    def inserer(self, order_id: int, pos: int) -> int:
        """Insère dans les arrêts restants ; renvoie la position correspondante dans la tournée complète."""
        idx = self.complet.index(self.restants[pos]) if pos < len(self.restants) else len(self.complet)
        # Même règle que l'application réelle (plans.deplacer_etat) : l'arrêt prend la rotation de celui qui le précède dans la tournée.
        voisin = self.complet[idx - 1] if idx else (self.complet[0] if self.complet else None)
        self.rotations[order_id] = self.rotations.get(voisin, self.rotation_depuis) if voisin is not None else self.rotation_depuis
        self.complet.insert(idx, order_id)
        self.restants.insert(pos, order_id)
        return idx


def construire(db: Session, plan: Plan, ctx: planning.Contexte, etat: dict, maintenant: datetime) -> list[Vivant]:
    now_min = minutes_du_jour(maintenant, plan.jour)
    suivi = livraisons.derniers_evenements(db, plan.id)
    vivants = []
    for r in etat["routes"]:
        ids = [a["order_id"] for a in r["arrets"]]
        rots = {a["order_id"]: a.get("rotation", 1) for a in r["arrets"]}
        prevu = planning.calculer_route(ctx, r["vehicle_id"], ids, r.get("conducteur_id"), [rots[i] for i in ids])
        statut = lambda i: (suivi.get(i) or {}).get("statut")  # noqa: E731
        faits = [i for i in ids if statut(i) in FINAUX]
        sur_place = next((i for i in ids if statut(i) == "arrive"), None)
        restants = [i for i in ids if i not in faits and i != sur_place]
        if sur_place is not None:
            ligne = ctx.ligne[sur_place]
            arrive = minutes_du_jour(suivi[sur_place]["arrive_le"], plan.jour)
            depuis = max(now_min, arrive + ctx.commandes[sur_place].service_min)  # service commencé à l'arrivée
        elif faits:
            ligne = ctx.ligne[faits[-1]]
            depuis = max(now_min, minutes_du_jour(suivi[faits[-1]]["termine_le"], plan.jour))
        else:
            ligne, depuis = 0, max(now_min, prevu.depart_min)  # pas encore parti : il part au plus tôt à l'heure prévue
        position = sur_place if sur_place is not None else (faits[-1] if faits else None)
        vivants.append(Vivant(r["vehicle_id"], r["verrouille"], r.get("conducteur_id"), ids, restants, ligne, depuis,
                              planning.chrono_a(prevu.activites, depuis), {a["order_id"] for a in r["arrets"] if a["verrouille"]}, rots,
                              rots[position] if position is not None else (rots[ids[0]] if ids else 1)))
    return vivants


def ajustements_trafic(ctx: planning.Contexte, vivants: list[Vivant], maintenant: datetime):
    """Durées de trajet observées en direct si le trafic est activé (désactivé par défaut). Renvoie (par véhicule, informations)."""
    f = trafic.fournisseur()
    if f is None:
        return None, {"actif": False, "fournisseur": None, "indisponible": False}
    sortie = {}
    try:
        for v in vivants:
            if not v.restants:
                continue
            lignes = [v.depuis_ligne, *[ctx.ligne[c] for c in v.restants], 0]
            pts = [ctx.positions[l] for l in lignes]
            m = f.durees(pts, pts, maintenant)
            table = {(lignes[i], lignes[j]): m[i][j] / 60 for i in range(len(lignes)) for j in range(len(lignes)) if m[i][j] is not None}
            sortie[v.vehicule_id] = lambda a, b, t=table: t.get((a, b))
    except trafic.TraficIndisponible:
        return None, {"actif": True, "fournisseur": f.nom, "indisponible": True}
    return sortie, {"actif": True, "fournisseur": f.nom, "indisponible": False}


@dataclass
class Evaluation:
    sims: dict[int, planning.Simulation]
    nb_retards: int
    retard_total: float
    km: float
    fermeture: float
    fin_max: float
    retards: list[tuple[int, int, float]]  # (vehicule, commande, retard en minutes)
    reportes: int = 0

    def cle(self):  # plus petit = meilleur ; on préfère ne rien reporter
        return (self.reportes, round(self.fermeture), self.nb_retards, round(self.retard_total), round(self.km, 1))

    def meilleur_que(self, autre: "Evaluation") -> bool:
        return (round(self.fermeture), self.nb_retards, round(self.retard_total)) < (round(autre.fermeture), autre.nb_retards, round(autre.retard_total))

    def impact(self) -> dict:
        return {"nb_retards": self.nb_retards, "retard_total_min": round(self.retard_total), "km": round(self.km, 1),
                "retour_max_min": round(self.fin_max), "apres_fermeture_min": round(self.fermeture), "reportes": self.reportes}


def evaluer(ctx: planning.Contexte, vivants: list[Vivant], ajust=None, reportes: int = 0) -> Evaluation:
    sims = {v.vehicule_id: planning.simuler_depuis(ctx, v.vehicule_id, v.restants, v.depuis_ligne, v.depuis_min, v.chrono, (ajust or {}).get(v.vehicule_id),
                                                   v.rotations_restantes(), v.rotation_depuis)
            for v in vivants}
    retards = [(vid, cid, m) for vid, s in sims.items() for cid, m in s.retards]
    return Evaluation(sims, len(retards), sum(m for _, _, m in retards), sum(s.distance_km for s in sims.values()),
                      sum(s.apres_fermeture_min for s in sims.values()), max((s.retour_min for s in sims.values() if s.arrets), default=0.0), retards, reportes)


@dataclass
class Proposition:
    titre: str
    description: str
    actions: list[dict]
    avant: Evaluation
    apres: Evaluation

    def sortie(self, index: int) -> dict:
        return {"index": index, "titre": self.titre, "description": self.description, "actions": self.actions,
                "impact": {"avant": self.avant.impact(), "apres": self.apres.impact()}}


def _nom(ctx: planning.Contexte, order_id: int) -> str:
    return ctx.commandes[order_id].reference


def _plaque(ctx: planning.Contexte, vehicule_id: int) -> str:
    return ctx.vehicules[vehicule_id].plaque


def _meilleure_position(ctx, vivants, cible: int, order_id: int, ajust, reportes=0):
    """Position (dans les arrêts restants du véhicule `cible`) qui minimise l'impact ; renvoie (pos, evaluation) ou None."""
    meilleur = None
    for pos in range(len(vivants[cible].restants) + 1):
        essai = [v.copie() for v in vivants]
        essai[cible].inserer(order_id, pos)
        e = evaluer(ctx, essai, ajust, reportes)
        if meilleur is None or e.cle() < meilleur[1].cle():
            meilleur = (pos, e)
    return meilleur


def _action(order_id: int, vehicule_id: int | None, position: int | None = None) -> dict:
    return {"order_id": order_id, "vehicle_id": vehicule_id, "position": position}


def _distinctes(propositions: list[Proposition], n: int = 3) -> list[Proposition]:
    """Les n meilleures propositions distinctes ; une variante qui reporte des arrêts est conservée si elle existe (choix de nature différente)."""
    vus, sortie = set(), []
    for p in sorted(propositions, key=lambda p: p.apres.cle()):
        signature = tuple((a["order_id"], a["vehicle_id"], a["position"]) for a in p.actions)
        if signature not in vus:
            vus.add(signature)
            sortie.append(p)
    retenues = sortie[:n]
    if len(sortie) > n and not any(p.apres.reportes for p in retenues):
        reporte = next((p for p in sortie[n:] if p.apres.reportes), None)
        if reporte:
            retenues[-1] = reporte
    return retenues


def propositions_retard(ctx, vivants, ajust=None) -> list[Proposition]:
    base = evaluer(ctx, vivants, ajust)
    if not base.retards:
        return []
    candidats: list[Proposition] = []
    for vid, cid, _ in sorted(base.retards, key=lambda r: -r[2])[:3]:
        i = next(k for k, v in enumerate(vivants) if v.vehicule_id == vid)
        if vivants[i].verrouille or cid in vivants[i].figes:
            continue
        # 1. Passer l'arrêt plus tôt dans la même tournée, 2. le confier à un autre camion.
        for cible, v in enumerate(vivants):
            if v.verrouille:
                continue
            essai = [x.copie() for x in vivants]
            essai[i].retirer(cid)
            res = _meilleure_position(ctx, essai, cible, cid, ajust)
            if res is None:
                continue
            pos, e = res
            essai[cible].inserer(cid, pos)
            if cible == i and essai[cible].restants == vivants[i].restants:
                continue
            idx = essai[cible].complet.index(cid)
            titre = (f"Passer {_nom(ctx, cid)} plus tôt dans la tournée de {_plaque(ctx, v.vehicule_id)}" if cible == i
                     else f"Confier {_nom(ctx, cid)} au camion {_plaque(ctx, v.vehicule_id)}")
            candidats.append(Proposition(titre, "", [_action(cid, v.vehicule_id, idx)], base, e))
        # 3. Reporter un arrêt sans fenêtre horaire qui précède l'arrêt en retard (libère du temps).
        for autre in vivants[i].restants[:vivants[i].restants.index(cid)]:
            c = ctx.commandes[autre]
            if c.fin_min is not None or c.debut_min is not None or autre in vivants[i].figes:
                continue
            essai = [x.copie() for x in vivants]
            essai[i].retirer(autre)
            e = evaluer(ctx, essai, ajust, reportes=1)
            candidats.append(Proposition(f"Reporter {_nom(ctx, autre)} (sans contrainte horaire) pour rattraper le retard", "", [_action(autre, None)], base, e))
    for p in candidats:
        if not p.apres.meilleur_que(base):
            p.titre = ""
    return _decrire(_distinctes([p for p in candidats if p.titre]), "retard")


def propositions_urgence(ctx, vivants, order_id: int, ajust=None) -> list[Proposition]:
    base = evaluer(ctx, vivants, ajust)
    candidats = []
    for cible, v in enumerate(vivants):
        if v.verrouille:
            continue
        res = _meilleure_position(ctx, vivants, cible, order_id, ajust)
        if res is None:
            continue
        pos, e = res
        essai = [x.copie() for x in vivants]
        idx = essai[cible].inserer(order_id, pos)
        candidats.append(Proposition(f"Insérer {_nom(ctx, order_id)} dans la tournée de {_plaque(ctx, v.vehicule_id)}, en position {pos + 1}", "",
                                     [_action(order_id, v.vehicule_id, idx)], base, e))
    return _decrire(_distinctes(candidats), "urgence")


def propositions_panne(ctx, vivants, vehicule_id: int, ajust=None) -> list[Proposition]:
    i = next((k for k, v in enumerate(vivants) if v.vehicule_id == vehicule_id), None)
    if i is None:
        return []
    base = evaluer(ctx, vivants, ajust)
    cassé = vivants[i]
    a_replacer = [c for c in cassé.restants if c not in cassé.figes]
    autres = [k for k, v in enumerate(vivants) if k != i and not v.verrouille]

    def strategie(ordre: list[int], tolerer_retards: bool, titre: str, seul: int | None = None) -> Proposition | None:
        essai = [x.copie() for x in vivants]
        for c in a_replacer:
            essai[i].retirer(c)
        actions, reportes = [], 0
        for c in ordre:
            options = [seul] if seul is not None else autres
            choix = None
            for cible in options:
                res = _meilleure_position(ctx, essai, cible, c, ajust, reportes)
                if res and (choix is None or res[1].cle() < choix[2].cle()):
                    choix = (cible, res[0], res[1])
            avant = evaluer(ctx, essai, ajust, reportes)
            if choix is None or (not tolerer_retards and choix[2].nb_retards > avant.nb_retards):
                actions.append(_action(c, None))  # ne passe pas sans créer de retard : laissé de côté, explicitement
                reportes += 1
                continue
            cible, pos, _ = choix
            idx = essai[cible].inserer(c, pos)
            actions.append(_action(c, essai[cible].vehicule_id, idx))
        if not actions:
            return None
        return Proposition(titre, "", actions, base, evaluer(ctx, essai, ajust, reportes))

    candidats = []
    if not a_replacer:
        return []
    par_fenetre = sorted(a_replacer, key=lambda c: ctx.commandes[c].fin_min if ctx.commandes[c].fin_min is not None else 24 * 60)
    for ordre, tolerer, titre in ((a_replacer, True, "Répartir les arrêts restants sur les autres camions, dans l'ordre prévu"),
                                  (par_fenetre, True, "Répartir en traitant d'abord les arrêts à fenêtre horaire"),
                                  (par_fenetre, False, "Répartir, en laissant de côté ce qui ne peut pas passer à l'heure")):
        p = strategie(ordre, tolerer, titre)
        if p:
            candidats.append(p)
    for cible in autres:
        p = strategie(a_replacer, True, f"Tout confier au camion {_plaque(ctx, vivants[cible].vehicule_id)}", seul=cible)
        if p:
            candidats.append(p)
    return _decrire(_distinctes(candidats), "panne")


def _decrire(propositions: list[Proposition], type_: str) -> list[Proposition]:
    for p in propositions:
        a, b = p.avant, p.apres
        morceaux = []
        if type_ != "urgence" or a.nb_retards != b.nb_retards:
            morceaux.append(f"retards : {a.nb_retards} → {b.nb_retards}")
        if round(b.km - a.km, 1):
            morceaux.append(f"distance restante {'+' if b.km >= a.km else '−'}{abs(round(b.km - a.km, 1)):g} km")
        if b.reportes:
            morceaux.append(f"{b.reportes} arrêt(s) reporté(s)")
        p.description = " · ".join(morceaux) or "Aucun changement d'impact"
    return propositions


# ---------------------------------------------------------------- Opérations complètes (lues par l'API)


def contexte_avec(db: Session, plan: Plan, order: Order | None):
    """Contexte du plan ; si `order` n'est pas dans les matrices (urgence), elles sont étendues en mémoire (appel au routage)."""
    ctx = plans.contexte(db, plan)
    if order is None or order.id in ctx.ligne:
        return ctx, None
    m = plan.matrices
    ids = m["commandes"] + [order.id]
    cmds = {o.id: o for o in db.scalars(select(Order).where(Order.company_id == plan.company_id, Order.id.in_(ids[1:])))}
    locs = [ctx.positions[0]] + [(cmds[i].lat, cmds[i].lng) for i in ids[1:]]
    profils = {}
    for cle, prof in m["profils"].items():
        v = db.get(Vehicle, prof["vehicle_ids"][0])
        profils[cle] = routage.options_camion(v)
    mats = matrices.fournisseur(locs, profils)
    nouveau = {"commandes": ids, "profils": {k: {"vehicle_ids": m["profils"][k]["vehicle_ids"], **mats[k]} for k in mats}}
    return plans.contexte(db, plan, nouveau), nouveau


def suivi(db: Session, plan: Plan, maintenant: datetime) -> dict:
    ctx = plans.contexte(db, plan)
    etat = plans.charger_etat(db, plan)
    vivants = construire(db, plan, ctx, etat, maintenant)
    ajust, info = ajustements_trafic(ctx, vivants, maintenant)
    ev = evaluer(ctx, vivants, ajust)
    plan_calc = {r.vehicule_id: r for r in plans._calculer(ctx, etat)}
    routes, retards = [], []
    for v in vivants:
        sim = ev.sims[v.vehicule_id]
        prevu = {a.commande_id: a for a in plan_calc[v.vehicule_id].arrets}
        late = dict(sim.retards)
        restants = []
        for a in sim.arrets:
            c = ctx.commandes[a.commande_id]
            ecart = a.arrivee_min - prevu[a.commande_id].arrivee_min
            restants.append({"order_id": c.id, "reference": c.reference, "arrivee_prevue_min": round(a.arrivee_min, 1),
                             "arrivee_plan_min": round(prevu[a.commande_id].arrivee_min, 1), "ecart_min": round(ecart, 1),
                             "fenetre_fin_min": c.fin_min, "retard_fenetre_min": round(late.get(c.id, 0), 1)})
            if c.id in late:
                retards.append({"vehicle_id": v.vehicule_id, "plaque": _plaque(ctx, v.vehicule_id), "order_id": c.id, "reference": c.reference,
                                "retard_min": round(late[c.id]), "message": f"{c.reference} : arrivée estimée à {planning.hhmm(a.arrivee_min)}, "
                                f"fenêtre close à {planning.hhmm(c.fin_min)} (retard de {planning.duree_txt(late[c.id])})"})
        lat, lng = ctx.positions.get(v.depuis_ligne, (None, None))
        routes.append({"vehicle_id": v.vehicule_id, "plaque": _plaque(ctx, v.vehicule_id), "verrouille": v.verrouille, "restants": restants,
                       "faits": len(v.complet) - len(v.restants), "retour_prevu_min": round(sim.retour_min, 1) if sim.arrets else None,
                       "apres_fermeture_min": round(sim.apres_fermeture_min), "depuis": {"lat": lat, "lng": lng, "min": round(v.depuis_min, 1)}})
    retards.sort(key=lambda r: -r["retard_min"])
    return {"maintenant": maintenant, "trafic": info, "routes": routes, "retards": retards,
            "resume": {"nb_retards": len(retards), "retard_total_min": round(ev.retard_total)}}


def proposer(db: Session, plan: Plan, type_: str, maintenant: datetime, order: Order | None = None, vehicule_id: int | None = None) -> list[dict]:
    """Propositions chiffrées. Lecture seule : ne modifie ni le plan ni les commandes."""
    ctx, _ = contexte_avec(db, plan, order if type_ == "urgence" else None)
    etat = plans.charger_etat(db, plan)
    vivants = construire(db, plan, ctx, etat, maintenant)
    ajust, _ = ajustements_trafic(ctx, vivants, maintenant)
    if type_ == "retard":
        props = propositions_retard(ctx, vivants, ajust)
    elif type_ == "urgence":
        props = propositions_urgence(ctx, vivants, order.id, ajust)
    else:
        props = propositions_panne(ctx, vivants, vehicule_id, ajust)
    return [p.sortie(i) for i, p in enumerate(props)]


def appliquer(db: Session, plan: Plan, type_: str, actions: list[dict], order: Order | None = None, vehicule_id: int | None = None):
    """Applique des actions explicitement validées : une seule étape d'historique (annulable)."""
    _, nouveau = contexte_avec(db, plan, order if type_ == "urgence" else None)
    etat = plans.charger_etat(db, plan)
    if nouveau is not None:  # commande urgente absente du plan : on étend les matrices puis on l'ajoute aux non affectées
        plan.matrices = nouveau
        etat["non_affectees"].append({"order_id": order.id, "raison": "Commande urgente"})
    for a in actions:
        etat = plans.deplacer_etat(etat, a["order_id"], a["vehicle_id"], a.get("position"))
    if type_ == "panne":
        route = next((r for r in etat["routes"] if r["vehicle_id"] == vehicule_id), None)
        if route is None:
            raise plans.ModificationRefusee("Véhicule absent de ce plan", 404)
        route["verrouille"] = True  # le camion en panne ne reçoit plus rien et l'optimiseur n'y touche plus
    libelle = {"retard": "Replanification (retard)", "urgence": "Commande urgente insérée", "panne": "Panne : arrêts redistribués"}[type_]
    plans.pousser(db, plan, etat, libelle)
