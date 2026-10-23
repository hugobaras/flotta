import json
import re
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import geocodage, tables
from .auth import current_user
from .db import get_db
from .models import ColumnMapping, Order, User

router = APIRouter(prefix="/api/admin/commandes")

# Champs importables : clé, libellé, obligatoire, noms de colonnes reconnus automatiquement.
CHAMPS = [
    ("reference", "Référence", True, ["reference", "ref", "numero", "n_commande", "commande", "bl"]),
    ("client", "Client", False, ["client", "destinataire", "nom", "raison_sociale"]),
    ("adresse", "Adresse", True, ["adresse", "adresse_livraison", "rue", "adresse_de_livraison"]),
    ("code_postal", "Code postal", False, ["code_postal", "cp", "postal"]),
    ("ville", "Ville", False, ["ville", "commune", "localite"]),
    ("poids_kg", "Poids (kg)", False, ["poids", "poids_kg", "kg"]),
    ("volume_m3", "Volume (m³)", False, ["volume", "volume_m3", "m3"]),
    ("palettes", "Palettes", False, ["palettes", "nb_palettes", "nombre_de_palettes"]),
    ("fenetre_debut", "Début de fenêtre", False, ["fenetre_debut", "debut", "heure_debut", "livraison_apres"]),
    ("fenetre_fin", "Fin de fenêtre", False, ["fenetre_fin", "fin", "heure_fin", "livraison_avant"]),
    ("duree_service_min", "Durée de service (min)", False, ["duree_service", "duree", "temps_de_service", "service_min"]),
    ("frigo", "Frigo", False, ["frigo", "frigorifique", "temperature_dirigee"]),
    ("adr", "ADR", False, ["adr", "matiere_dangereuse"]),
    ("hayon", "Hayon", False, ["hayon"]),
    ("contact_nom", "Contact sur place", False, ["contact", "contact_nom", "interlocuteur"]),
    ("contact_telephone", "Téléphone du contact", False, ["telephone", "tel", "contact_telephone", "mobile"]),
    ("consignes", "Consignes de livraison", False, ["consignes", "instructions", "commentaire", "remarques"]),
    ("date_livraison", "Date de livraison", False, ["date", "date_livraison", "livraison"]),
]
CLES = [c[0] for c in CHAMPS]
HEURE = re.compile(r"^(\d{1,2})\s*(?:[:hH]\s*(\d{2})?)?$")


def parse_heure(texte: str) -> str | None:
    t = texte.strip()
    if not t:
        return None
    m = HEURE.match(t)
    if not m:
        raise ValueError("heure attendue (08:00, 8h30)")
    h, mn = int(m.group(1)), int(m.group(2) or 0)
    if h > 23 or mn > 59:
        raise ValueError("heure invalide")
    return f"{h:02d}:{mn:02d}"


def parse_date(texte: str) -> date | None:
    t = texte.strip()
    if not t:
        return None
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%d.%m.%Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%y"):
        try:
            return datetime.strptime(t, fmt).date()
        except ValueError:
            continue
    raise ValueError("date attendue (jj/mm/aaaa)")


class CommandeIn(BaseModel):
    reference: str = Field(min_length=1, max_length=60)
    client: str = Field(default="", max_length=150)
    adresse: str = Field(min_length=3, max_length=300)
    poids_kg: int = Field(default=0, ge=0, le=60000)
    volume_m3: float = Field(default=0, ge=0, le=200)
    palettes: int = Field(default=0, ge=0, le=60)
    fenetre_debut: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    fenetre_fin: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duree_service_min: int = Field(default=15, ge=0, le=480)
    frigo: bool = False
    adr: bool = False
    hayon: bool = False
    contact_nom: str = Field(default="", max_length=100)
    contact_telephone: str = Field(default="", max_length=30)
    consignes: str = Field(default="", max_length=500)
    date_livraison: date

    @model_validator(mode="after")
    def fenetre_coherente(self):
        if self.fenetre_debut and self.fenetre_fin and self.fenetre_debut >= self.fenetre_fin:
            raise ValueError("La fenêtre de livraison doit finir après son début")
        return self


def sortie(o: Order) -> dict:
    return {"id": o.id, "reference": o.reference, "client": o.client, "adresse": o.adresse, "lat": o.lat, "lng": o.lng,
            "geo_statut": o.geo_statut, "geo_score": o.geo_score, "poids_kg": o.poids_kg, "volume_m3": o.volume_m3,
            "palettes": o.palettes, "fenetre_debut": o.fenetre_debut, "fenetre_fin": o.fenetre_fin,
            "duree_service_min": o.duree_service_min, "frigo": o.frigo, "adr": o.adr, "hayon": o.hayon,
            "contact_nom": o.contact_nom, "contact_telephone": o.contact_telephone, "consignes": o.consignes,
            "date_livraison": o.date_livraison, "statut": o.statut}


def _appliquer_geo(o: Order, res: geocodage.Resultat):
    o.lat, o.lng, o.geo_score, o.geo_statut = res.lat, res.lng, res.score, res.statut


def _commande(db: Session, user: User, order_id: int) -> Order:
    o = db.scalar(select(Order).where(Order.id == order_id, Order.company_id == user.company_id))
    if not o:
        raise HTTPException(404, "Commande inconnue")
    return o


@router.get("")
def lister(date_: date | None = Query(default=None, alias="date"), geo: str | None = None, q: str | None = None, user: User = Depends(current_user),
           db: Session = Depends(get_db)):
    req = select(Order).where(Order.company_id == user.company_id)
    if date_:
        req = req.where(Order.date_livraison == date_)
    if geo:
        req = req.where(Order.geo_statut == geo)
    if q:
        req = req.where(Order.reference.icontains(q, autoescape=True) | Order.client.icontains(q, autoescape=True)
                        | Order.adresse.icontains(q, autoescape=True))
    return [sortie(o) for o in db.scalars(req.order_by(Order.date_livraison.desc(), Order.reference).limit(2000))]


@router.post("", status_code=201)
def creer(body: CommandeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.scalar(select(Order.id).where(Order.company_id == user.company_id, Order.reference == body.reference,
                                        Order.date_livraison == body.date_livraison)):
        raise HTTPException(409, "Une commande porte déjà cette référence ce jour-là")
    o = Order(company_id=user.company_id, **body.model_dump())
    try:
        _appliquer_geo(o, geocodage.geocoder_une(db, o.adresse))
    except geocodage.GeocodageIndisponible:
        pass  # la commande est créée, le géocodage sera relancé
    db.add(o)
    db.commit()
    return sortie(o)


class CommandePatch(BaseModel):
    client: str | None = Field(default=None, max_length=150)
    adresse: str | None = Field(default=None, min_length=3, max_length=300)
    poids_kg: int | None = Field(default=None, ge=0, le=60000)
    volume_m3: float | None = Field(default=None, ge=0, le=200)
    palettes: int | None = Field(default=None, ge=0, le=60)
    fenetre_debut: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    fenetre_fin: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duree_service_min: int | None = Field(default=None, ge=0, le=480)
    frigo: bool | None = None
    adr: bool | None = None
    hayon: bool | None = None
    contact_nom: str | None = Field(default=None, max_length=100)
    contact_telephone: str | None = Field(default=None, max_length=30)
    consignes: str | None = Field(default=None, max_length=500)
    statut: str | None = Field(default=None, pattern=r"^(a_planifier|planifie|livre|echec|annule)$")
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def position_complete(self):
        if (self.lat is None) != (self.lng is None):
            raise ValueError("Position incomplète : latitude et longitude vont ensemble")
        return self


@router.patch("/{order_id}")
def modifier(order_id: int, body: CommandePatch, user: User = Depends(current_user), db: Session = Depends(get_db)):
    o = _commande(db, user, order_id)
    champs = body.model_dump(exclude_unset=True)
    lat, lng = champs.pop("lat", None), champs.pop("lng", None)
    adresse_changee = "adresse" in champs and champs["adresse"] != o.adresse
    for k, v in champs.items():
        if v is not None or k in ("fenetre_debut", "fenetre_fin"):
            setattr(o, k, v)
    if o.fenetre_debut and o.fenetre_fin and o.fenetre_debut >= o.fenetre_fin:
        raise HTTPException(422, "La fenêtre de livraison doit finir après son début")
    if lat is not None:  # correction à la main (clic sur la carte)
        o.lat, o.lng, o.geo_score, o.geo_statut = lat, lng, 1.0, "manuel"
    elif adresse_changee:
        o.lat = o.lng = o.geo_score = None
        o.geo_statut = "a_geocoder"
        try:
            _appliquer_geo(o, geocodage.geocoder_une(db, o.adresse))
        except geocodage.GeocodageIndisponible:
            pass
    db.commit()
    return sortie(o)


@router.delete("/{order_id}", status_code=204)
def supprimer(order_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_commande(db, user, order_id))
    db.commit()
    return Response(status_code=204)


@router.post("/geocoder")
def relancer_geocodage(date_: date | None = Query(default=None, alias="date"), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Géocode les commandes encore en attente (service indisponible lors de l'import)."""
    req = select(Order).where(Order.company_id == user.company_id, Order.geo_statut == "a_geocoder")
    if date_:
        req = req.where(Order.date_livraison == date_)
    attente = list(db.scalars(req))
    if not attente:
        return {"traitees": 0}
    try:
        res = geocodage.geocoder_lot(db, [o.adresse for o in attente])
    except geocodage.GeocodageIndisponible:
        raise HTTPException(503, "Le service de géocodage est indisponible, réessayez plus tard")
    for o in attente:
        _appliquer_geo(o, res[geocodage.normaliser(o.adresse)])
    db.commit()
    return {"traitees": len(attente)}


# --- Import CSV / Excel avec mappage de colonnes ---


def _proposer(entetes: list[str], enregistre: dict | None) -> dict[str, str]:
    """Mappage proposé : celui mémorisé par la société s'il s'applique, sinon une détection par nom de colonne."""
    propose: dict[str, str] = {}
    normales = {tables.normaliser(e): e for e in entetes}
    for cle, _, _, alias in CHAMPS:
        sauvegarde = (enregistre or {}).get(cle)
        if sauvegarde in entetes:
            propose[cle] = sauvegarde
        else:
            trouve = next((normales[a] for a in alias if a in normales), None)
            if trouve:
                propose[cle] = trouve
    return propose


def _mapping_societe(db: Session, company_id: int) -> dict | None:
    m = db.scalar(select(ColumnMapping).where(ColumnMapping.company_id == company_id))
    return m.mapping if m else None


async def _fichier(fichier: UploadFile):
    return tables.lire_tableau(await fichier.read(tables.MAX_BYTES + 1), fichier.filename or "")


def _lire_mapping(brut: str, entetes: list[str]) -> dict[str, str]:
    try:
        mapping = json.loads(brut)
        assert isinstance(mapping, dict)
    except (ValueError, AssertionError):
        raise HTTPException(422, "Mappage de colonnes illisible")
    propre = {}
    for cle, col in mapping.items():
        if cle not in CLES:
            raise HTTPException(422, f"Champ inconnu : {cle}")
        if col:
            if col not in entetes:
                raise HTTPException(422, f"Colonne introuvable dans le fichier : {col}")
            propre[cle] = col
    for cle, libelle, obligatoire, _ in CHAMPS:
        if obligatoire and cle not in propre:
            raise HTTPException(422, f"Associez une colonne au champ « {libelle} »")
    if "adresse" not in propre:
        raise HTTPException(422, "Associez une colonne au champ « Adresse »")
    return propre


@router.post("/import/colonnes")
async def colonnes(fichier: UploadFile = File(), user: User = Depends(current_user), db: Session = Depends(get_db)):
    entetes, lignes = await _fichier(fichier)
    return {"entetes": entetes, "exemple": lignes[:3], "total": len(lignes),
            "mapping_propose": _proposer(entetes, _mapping_societe(db, user.company_id)),
            "champs": [{"cle": c, "libelle": l, "obligatoire": o} for c, l, o, _ in CHAMPS]}


def _analyser(entetes, lignes, mapping, date_defaut: date | None, user: User, db: Session):
    index = {cle: entetes.index(col) for cle, col in mapping.items()}
    existantes = {(o.reference, o.date_livraison): o for o in db.scalars(select(Order).where(Order.company_id == user.company_id))}
    vues, rapport = set(), []
    for n, ligne in enumerate(lignes, start=2):
        brut = {cle: (ligne[i] if i < len(ligne) else "").strip() for cle, i in index.items()}
        erreurs, v = [], {}
        try:
            v["reference"] = brut.get("reference", "")
            v["client"] = brut.get("client", "")
            for cle in ("contact_nom", "contact_telephone", "consignes"):
                if brut.get(cle):
                    v[cle] = brut[cle]
            adresse = " ".join(x for x in (brut.get("adresse"), brut.get("code_postal"), brut.get("ville")) if x)
            v["adresse"] = adresse
            for cle in ("poids_kg", "palettes", "duree_service_min"):
                x = tables.nombre(brut.get(cle, "")) if cle in brut else None
                if x is not None and x != int(x):
                    raise ValueError(f"{cle} : entier attendu")
                if x is not None:
                    v[cle] = int(x)
            if "volume_m3" in brut and (x := tables.nombre(brut["volume_m3"])) is not None:
                v["volume_m3"] = x
            for cle in ("frigo", "adr", "hayon"):
                if cle in brut:
                    v[cle] = tables.booleen(brut[cle])
            v["fenetre_debut"] = parse_heure(brut.get("fenetre_debut", ""))
            v["fenetre_fin"] = parse_heure(brut.get("fenetre_fin", ""))
            jour = parse_date(brut.get("date_livraison", "")) or date_defaut
            if jour is None:
                raise ValueError("date_livraison : aucune date dans le fichier ni par défaut")
            v["date_livraison"] = jour
        except ValueError as e:
            erreurs.append(str(e))
        modele = None
        if not erreurs:
            try:
                modele = CommandeIn(**v)
            except Exception as e:
                erreurs = [f"{'.'.join(map(str, err['loc']))} : {err['msg'].removeprefix('Value error, ')}"
                           for err in getattr(e, "errors", lambda: [{"loc": ["ligne"], "msg": str(e)}])()]
        action = None
        if modele:
            cle_unique = (modele.reference, modele.date_livraison)
            if cle_unique in vues:
                erreurs.append("reference : déjà présente plus haut dans le fichier pour ce jour")
            else:
                vues.add(cle_unique)
                action = "mettre_a_jour" if cle_unique in existantes else "creer"
        rapport.append({"ligne": n, "reference": v.get("reference", ""), "erreurs": erreurs,
                        "action": None if erreurs else action, "_modele": None if erreurs else modele})
    return rapport


def _public(rapport):
    return [{k: x for k, x in r.items() if k != "_modele"} for r in rapport]


async def _preparer(fichier, mapping, date_defaut, user, db):
    entetes, lignes = await _fichier(fichier)
    carte = _lire_mapping(mapping, entetes)
    jour = None
    if date_defaut:
        try:
            jour = date.fromisoformat(date_defaut)
        except ValueError:
            raise HTTPException(422, "Date par défaut invalide (aaaa-mm-jj)")
    return carte, _analyser(entetes, lignes, carte, jour, user, db)


@router.post("/import/apercu")
async def apercu(fichier: UploadFile = File(), mapping: str = Form(), date_defaut: str | None = Form(default=None),
                 user: User = Depends(current_user), db: Session = Depends(get_db)):
    _, rapport = await _preparer(fichier, mapping, date_defaut, user, db)
    ok = sum(1 for r in rapport if not r["erreurs"])
    return {"lignes": _public(rapport), "total": len(rapport), "valides": ok, "en_erreur": len(rapport) - ok}


@router.post("/import")
async def importer(fichier: UploadFile = File(), mapping: str = Form(), date_defaut: str | None = Form(default=None),
                   memoriser: bool = Form(default=True), user: User = Depends(current_user), db: Session = Depends(get_db)):
    carte, rapport = await _preparer(fichier, mapping, date_defaut, user, db)
    valides: list[Order] = []
    crees = misajour = 0
    for r in rapport:
        m: CommandeIn | None = r["_modele"]
        if not m:
            continue
        existante = db.scalar(select(Order).where(Order.company_id == user.company_id, Order.reference == m.reference,
                                                  Order.date_livraison == m.date_livraison))
        if existante:
            adresse_changee = existante.adresse != m.adresse
            for k, val in m.model_dump().items():
                setattr(existante, k, val)
            if adresse_changee:
                existante.lat = existante.lng = existante.geo_score = None
                existante.geo_statut = "a_geocoder"
            misajour += 1
            valides.append(existante)
        else:
            o = Order(company_id=user.company_id, **m.model_dump())
            db.add(o)
            valides.append(o)
            crees += 1
    if memoriser:
        enreg = db.scalar(select(ColumnMapping).where(ColumnMapping.company_id == user.company_id))
        if enreg:
            enreg.mapping = carte
        else:
            db.add(ColumnMapping(company_id=user.company_id, mapping=carte))
    db.flush()
    # Géocodage en lot, avec cache ; un service indisponible n'empêche pas l'import.
    a_faire = [o for o in valides if o.geo_statut == "a_geocoder"]
    geo_indisponible = False
    if a_faire:
        try:
            res = geocodage.geocoder_lot(db, [o.adresse for o in a_faire])
            for o in a_faire:
                _appliquer_geo(o, res[geocodage.normaliser(o.adresse)])
        except geocodage.GeocodageIndisponible:
            geo_indisponible = True
    db.commit()
    comptes = {s: sum(1 for o in valides if o.geo_statut == s) for s in ("ok", "douteux", "introuvable", "a_geocoder", "manuel")}
    return {"crees": crees, "mis_a_jour": misajour, "ignores": sum(1 for r in rapport if r["erreurs"]),
            "geocodage": comptes, "geocodage_indisponible": geo_indisponible, "lignes": _public(rapport)}
