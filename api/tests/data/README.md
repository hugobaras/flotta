# Cas réels de routage

Pour valider le routage poids lourd sur un cas réel de votre région, ajoutez `pont_bas.json` dans ce dossier :

```json
{
  "depart": {"lat": 47.2184, "lng": -1.5536},
  "arrivee": {"lat": 47.2500, "lng": -1.5000},
  "pont": {"lat": 47.2300, "lng": -1.5300, "hauteur_m": 3.5},
  "hauteur_trop_haute_m": 4.0,
  "hauteur_compatible_m": 3.2
}
```

Puis lancez les tests avec un Valhalla chargé des tuiles France :
`VALHALLA_URL=http://localhost:8002 pytest tests/test_routage_reel.py`

Le test vérifie qu'un camion de `hauteur_trop_haute_m` ne passe pas par `pont` (itinéraire différent ou refus), et qu'un camion de `hauteur_compatible_m` peut l'emprunter.
