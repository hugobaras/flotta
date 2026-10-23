import os
import re
import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, BeforeValidator, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import tables
from .auth import current_user
from .checklists import create_default_template
from .db import get_db
from .models import Check, ChecklistTemplate, Driver, User, Vehicle
from .qr import planche_qr


router = APIRouter(prefix="/api/admin")
TYPES = ["poids_lourd", "porteur", "semi_remorque", "utilitaire"]
PLAQUE = re.compile(r"^[A-Z0-9][A-Z0-9 \-]{1,18}[A-Z0-9]$")


def _vide_en_none(v):
    return None if isinstance(v, str) and not v.strip() else v


Opt = BeforeValidator(_vide_en_none)


def _borne(type_, ge, le):
    """Nombre facultatif borné : une cellule vide devient None, sans passer par les bornes."""
    return Annotated[Annotated[type_, Field(ge=ge, le=le)] | None, Opt]


class VehicleIn(BaseModel):
    plaque: str
    type: str = "poids_lourd"
    actif: bool = True
    hauteur_m: _borne(float, 1, 5) = None
    largeur_m: _borne(float, 1, 3.5) = None
    longueur_m: _borne(float, 2, 25) = None
    ptac_kg: _borne(int, 500, 60000) = None
    charge_utile_kg: _borne(int, 0, 60000) = None
    essieux: _borne(int, 2, 9) = None
    palettes: _borne(int, 0, 60) = None
    capacite_kg: _borne(int, 0, 60000) = None
    capacite_m3: _borne(float, 0, 200) = None
    adr: bool = False
    frigo: bool = False

    @field_validator("plaque")
    @classmethod
    def plaque_valide(cls, v: str) -> str:
        v = re.sub(r"\s+", " ", v.strip().upper())
        if not PLAQUE.match(v):
            raise ValueError("Plaque invalide (lettres, chiffres, tirets)")
        return v

    @field_validator("type")
    @classmethod
    def type_valide(cls, v: str) -> str:
        if v not in TYPES:
            raise ValueError(f"Type inconnu : {', '.join(TYPES)}")
        return v


class VehiclePatch(BaseModel):
    """Mise à jour partielle : seuls les champs envoyés changent."""
    plaque: str | None = None
    type: str | None = None
    actif: bool | None = None
    hauteur_m: _borne(float, 1, 5) = None
    largeur_m: _borne(float, 1, 3.5) = None
    longueur_m: _borne(float, 2, 25) = None
    ptac_kg: _borne(int, 500, 60000) = None
    charge_utile_kg: _borne(int, 0, 60000) = None
    essieux: _borne(int, 2, 9) = None
    palettes: _borne(int, 0, 60) = None
    capacite_kg: _borne(int, 0, 60000) = None
    capacite_m3: _borne(float, 0, 200) = None
    adr: bool | None = None
    frigo: bool | None = None

    @field_validator("plaque")
    @classmethod
    def plaque_valide(cls, v):
        return None if v is None else VehicleIn.plaque_valide(v)

    @field_validator("type")
    @classmethod
    def type_valide(cls, v):
        return None if v is None else VehicleIn.type_valide(v)


CHAMPS = list(VehicleIn.model_fields)


def sortie(v: Vehicle) -> dict:
    return {"id": v.id, "token": v.token, "bloque": v.bloque, **{c: getattr(v, c) for c in CHAMPS}}


def _jeton(db: Session) -> str:
    while True:
        t = secrets.token_urlsafe(9)
        if not db.scalar(select(Vehicle.id).where(Vehicle.token == t)):
            return t


def _modele_existe(db: Session, company_id: int, type_: str):
    if not db.scalar(select(ChecklistTemplate.id).where(
            ChecklistTemplate.company_id == company_id, ChecklistTemplate.vehicle_type == type_)):
        create_default_template(db, company_id, type_)


def _doublon(db: Session, company_id: int, plaque: str, sauf_id: int | None = None) -> bool:
    q = select(Vehicle.id).where(Vehicle.company_id == company_id, Vehicle.plaque == plaque)
    if sauf_id:
        q = q.where(Vehicle.id != sauf_id)
    return db.scalar(q) is not None


def _vehicule(db: Session, user: User, vehicle_id: int) -> Vehicle:
    v = db.scalar(select(Vehicle).where(Vehicle.id == vehicle_id, Vehicle.company_id == user.company_id))
    if not v:
        raise HTTPException(404, "Véhicule inconnu")
    return v


@router.get("/vehicules")
def list_vehicules(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Vehicle).where(Vehicle.company_id == user.company_id).order_by(Vehicle.plaque))
    return [sortie(v) for v in rows]


@router.post("/vehicules", status_code=201)
def create_vehicule(body: VehicleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if _doublon(db, user.company_id, body.plaque):
        raise HTTPException(409, "Cette plaque existe déjà")
    v = Vehicle(company_id=user.company_id, token=_jeton(db), **body.model_dump())
    db.add(v)
    _modele_existe(db, user.company_id, v.type)
    db.commit()
    return sortie(v)


@router.patch("/vehicules/{vehicle_id}")
def patch_vehicule(vehicle_id: int, body: VehiclePatch, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    v = _vehicule(db, user, vehicle_id)
    champs = body.model_dump(exclude_unset=True)
    if "plaque" in champs and champs["plaque"] is None:
        raise HTTPException(422, "La plaque ne peut pas être vide")
    if "plaque" in champs and _doublon(db, user.company_id, champs["plaque"], v.id):
        raise HTTPException(409, "Cette plaque existe déjà")
    for k, val in champs.items():
        if val is None and k in ("type", "actif", "adr", "frigo"):
            continue  # ces champs ne sont jamais vides
        setattr(v, k, val)
    _modele_existe(db, user.company_id, v.type)
    db.commit()
    return sortie(v)


@router.delete("/vehicules/{vehicle_id}", status_code=204)
def delete_vehicule(vehicle_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    v = _vehicule(db, user, vehicle_id)
    if db.scalar(select(Check.id).where(Check.vehicle_id == v.id)):
        raise HTTPException(409, "Ce véhicule a un historique de contrôles : désactivez-le plutôt que de le supprimer")
    for d in db.scalars(select(Driver).where(Driver.vehicule_habituel_id == v.id)):
        d.vehicule_habituel_id = None
    db.delete(v)
    db.commit()
    return Response(status_code=204)


# --- Import CSV / Excel ---

ALIAS = {
    "plaque": ["plaque", "immatriculation", "immat"], "type": ["type", "type_de_vehicule"],
    "actif": ["actif", "en_service"], "hauteur_m": ["hauteur", "hauteur_m"], "largeur_m": ["largeur", "largeur_m"],
    "longueur_m": ["longueur", "longueur_m"], "ptac_kg": ["ptac", "ptac_kg"],
    "charge_utile_kg": ["charge_utile", "charge_utile_kg"], "essieux": ["essieux", "nombre_d_essieux", "nb_essieux"],
    "palettes": ["palettes", "capacite_palettes", "nb_palettes"], "capacite_kg": ["capacite_kg", "kg"],
    "capacite_m3": ["capacite_m3", "m3", "volume", "volume_m3"], "adr": ["adr"], "frigo": ["frigo", "frigorifique"],
}
NOMBRES = {"hauteur_m", "largeur_m", "longueur_m", "capacite_m3"}
ENTIERS = {"ptac_kg", "charge_utile_kg", "essieux", "palettes", "capacite_kg"}
BOOLEENS = {"adr", "frigo", "actif"}


def analyser(entetes: list[str], lignes: list[list[str]], user: User, db: Session):
    """Rapport ligne par ligne, sans rien écrire."""
    index: dict[str, int] = {}
    reconnues, ignorees = [], []
    for i, e in enumerate(entetes):
        n = tables.normaliser(e)
        champ = next((c for c, alias in ALIAS.items() if n in alias), None)
        if champ and champ not in index:
            index[champ] = i
            reconnues.append(e)
        else:
            ignorees.append(e)
    if "plaque" not in index:
        raise HTTPException(422, "Colonne « plaque » introuvable dans le fichier")
    existantes = {v.plaque: v.id for v in db.scalars(select(Vehicle).where(Vehicle.company_id == user.company_id))}
    vues: set[str] = set()
    rapport = []
    for n, ligne in enumerate(lignes, start=2):  # ligne 1 = en-têtes
        brut = {c: (ligne[i] if i < len(ligne) else "") for c, i in index.items()}
        erreurs, valeurs = [], {}
        for champ, texte in brut.items():
            try:
                if champ in NOMBRES:
                    valeurs[champ] = tables.nombre(texte)
                elif champ in ENTIERS:
                    x = tables.nombre(texte)
                    if x is not None and x != int(x):
                        raise ValueError("entier attendu")
                    valeurs[champ] = None if x is None else int(x)
                elif champ in BOOLEENS:
                    valeurs[champ] = tables.booleen(texte) if texte.strip() or champ != "actif" else True
                else:
                    valeurs[champ] = texte.strip()
            except ValueError as e:
                erreurs.append(f"{champ} : {e if str(e) != '' and 'could not' not in str(e) else 'valeur non numérique'}")
        modele = None
        if not erreurs:
            try:
                modele = VehicleIn(**valeurs)
            except Exception as e:  # erreurs de validation pydantic, une par champ
                erreurs = [f"{'.'.join(map(str, err['loc']))} : {err['msg'].removeprefix('Value error, ')}"
                           for err in getattr(e, "errors", lambda: [{"loc": ["ligne"], "msg": str(e)}])()]
        action = None
        if modele and modele.plaque in vues:
            erreurs.append("plaque : déjà présente plus haut dans le fichier")
        elif modele:
            vues.add(modele.plaque)
            action = "mettre_a_jour" if modele.plaque in existantes else "creer"
        rapport.append({"ligne": n, "plaque": valeurs.get("plaque", ""), "erreurs": erreurs,
                        "action": None if erreurs else action, "_modele": None if erreurs else modele})
    return reconnues, ignorees, rapport


async def _lire(fichier: UploadFile):
    data = await fichier.read(tables.MAX_BYTES + 1)
    return tables.lire_tableau(data, fichier.filename or "")


def _public(rapport):
    return [{k: v for k, v in r.items() if k != "_modele"} for r in rapport]


@router.post("/vehicules/import/apercu")
async def apercu_import(fichier: UploadFile = File(), user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    entetes, lignes = await _lire(fichier)
    reconnues, ignorees, rapport = analyser(entetes, lignes, user, db)
    ok = sum(1 for r in rapport if not r["erreurs"])
    return {"colonnes_reconnues": reconnues, "colonnes_ignorees": ignorees, "lignes": _public(rapport),
            "total": len(rapport), "valides": ok, "en_erreur": len(rapport) - ok}


@router.post("/vehicules/import")
async def importer(fichier: UploadFile = File(), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Importe les lignes valides ; celles en erreur sont ignorées et listées dans le rapport."""
    entetes, lignes = await _lire(fichier)
    _, _, rapport = analyser(entetes, lignes, user, db)
    crees = misajour = 0
    for r in rapport:
        m: VehicleIn | None = r["_modele"]
        if not m:
            continue
        existant = db.scalar(select(Vehicle).where(Vehicle.company_id == user.company_id, Vehicle.plaque == m.plaque))
        if existant:
            for k, val in m.model_dump(exclude_unset=True).items():
                setattr(existant, k, val)
            misajour += 1
        else:
            db.add(Vehicle(company_id=user.company_id, token=_jeton(db), **m.model_dump()))
            db.flush()
            crees += 1
        _modele_existe(db, user.company_id, m.type)
    db.commit()
    return {"crees": crees, "mis_a_jour": misajour, "ignores": sum(1 for r in rapport if r["erreurs"]),
            "lignes": _public(rapport)}


# --- Planches de QR codes ---


@router.get("/vehicules/qr.pdf")
def planches_qr(ids: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Vehicle).where(Vehicle.company_id == user.company_id, Vehicle.actif.is_(True)).order_by(Vehicle.plaque)
    if ids:
        try:
            q = q.where(Vehicle.id.in_([int(i) for i in ids.split(",") if i]))
        except ValueError:
            raise HTTPException(422, "ids : liste de nombres attendue")
    vehicules = [(v.plaque, v.token) for v in db.scalars(q)]
    if not vehicules:
        raise HTTPException(404, "Aucun véhicule à imprimer")
    pdf = planche_qr(vehicules, os.getenv("APP_URL", "http://localhost:3000"))
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="qr-vehicules.pdf"'})
