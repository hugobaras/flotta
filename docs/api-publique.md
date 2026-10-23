# API publique Flotta (offre Pro)

Documentation interactive : `/api/v1/docs` (schéma OpenAPI : `/api/v1/openapi.json`).

## Authentification

Un administrateur crée une clé dans **Réglages → Intégrations**. La clé (`flt_…`) n'est affichée qu'une fois ; seule son empreinte est stockée. Elle se révoque à tout moment.
Chaque requête porte `Authorization: Bearer flt_…`. Limite : 120 requêtes par minute et par clé (réponse `429` avec `Retry-After`).

```bash
curl -H "Authorization: Bearer $FLOTTA_CLE" "https://flotta.example/api/v1/commandes?date=2026-11-02"

curl -X POST -H "Authorization: Bearer $FLOTTA_CLE" -H "Content-Type: application/json" \
  -d '{"reference":"CMD-1","client":"Acme","adresse":"1 rue de la Paix, Nantes","date_livraison":"2026-11-02","palettes":2}' \
  https://flotta.example/api/v1/commandes
```

```python
import httpx
r = httpx.post("https://flotta.example/api/v1/commandes", headers={"Authorization": f"Bearer {CLE}"},
               json={"reference": "CMD-1", "client": "Acme", "adresse": "1 rue de la Paix, Nantes", "date_livraison": "2026-11-02"})
r.raise_for_status()
```

Ressources : `GET/POST /commandes`, `GET/PATCH /commandes/{id}`, `GET /plans`, `GET /plans/{id}` (tournées, arrêts, avancement), `GET /controles?date=`.

## Webhooks

Réglages → Intégrations : une adresse **HTTPS publique** et les événements souhaités (`plan.publie`, `arret.livre`, `controle.defaut_critique`). Le secret (`whsec_…`) n'est affiché qu'une fois.

Chaque appel est un `POST` JSON avec les en-têtes `X-Flotta-Evenement`, `X-Flotta-Livraison` (identifiant, utile pour dédoublonner) et `X-Flotta-Signature: t=<horodatage>,v1=<hmac>`, où `hmac = HMAC-SHA256(secret, "<t>." + corps_brut)`.
Vérifiez la signature **sur le corps brut** et rejetez si `t` date de plus de 5 minutes.

Réponse `2xx` attendue sous 10 s. Sinon réessais à 1 min, 5 min, 30 min, 2 h puis 12 h (6 tentatives au total), puis abandon ; l'historique est visible dans l'interface.
Les adresses privées (réseau interne, métadonnées cloud) sont refusées à l'enregistrement et à chaque envoi.

```python
import hashlib, hmac, time
def verifier(secret: str, entete: str, corps: bytes) -> bool:
    p = dict(x.split("=", 1) for x in entete.split(","))
    if abs(time.time() - int(p["t"])) > 300:
        return False
    attendu = hmac.new(secret.encode(), p["t"].encode() + b"." + corps, hashlib.sha256).hexdigest()
    return hmac.compare_digest(attendu, p["v1"])
```

Un script complet (création d'une commande puis réception d'un webhook) : `exemples/api_et_webhook.py`.
