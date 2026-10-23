import pytest

from app.planning import (CommandeInfo, Contexte, VehiculeInfo, calculer_route, indicateurs)


def matrice(*positions_km):
    pts = [0, *positions_km]
    return [[int(abs(a - b) * 60) for b in pts] for a in pts]  # 60 s par km


def contexte(commandes, vehicules=None, positions=None, **kw):
    positions = positions or [10 * (i + 1) for i in range(len(commandes))]
    m = matrice(*positions)
    km = [[abs(a - b) / 1.0 for b in [0, *positions]] for a in [0, *positions]]
    return Contexte(kw.get("ouverture", 6 * 60), kw.get("fermeture", 19 * 60), kw.get("duree_max", 600),
                    {c.id: c for c in commandes}, {v.id: v for v in (vehicules or [VehiculeInfo(1, "AA-111-AA", "A")])},
                    {c.id: i + 1 for i, c in enumerate(commandes)}, {"A": m}, {"A": km})


def cmd(i, **kw):
    return CommandeInfo(i, f"R{i}", **kw)


def test_arrival_times_use_travel_and_service_times():
    ctx = contexte([cmd(1, service_min=30), cmd(2, service_min=15)], positions=[10, 20])
    r = calculer_route(ctx, 1, [1, 2])
    a, b = r.arrets
    assert (a.arrivee_min, a.depart_min) == (r.depart_min + 10, r.depart_min + 40)
    assert b.arrivee_min == a.depart_min + 10 and r.retour_min == b.depart_min + 20
    assert r.distance_km == 40 and r.trajet_s == 40 * 60 and r.alertes == []


def test_start_is_delayed_to_remove_waiting_before_first_stop():
    ctx = contexte([cmd(1, debut_min=9 * 60, fin_min=11 * 60)], positions=[30])
    r = calculer_route(ctx, 1, [1])
    assert r.arrets[0].arrivee_min == 9 * 60 and r.depart_min == 8 * 60 + 30 and r.arrets[0].attente_min == 0


def test_waiting_between_stops_is_absorbed_by_leaving_later():
    ctx = contexte([cmd(1), cmd(2, debut_min=12 * 60)], positions=[10, 20])
    avant = 6 * 60 + 35  # sans décalage : arrivée à 6 h 35 au 2e arrêt, 325 min d'attente avant 12 h
    r = calculer_route(ctx, 1, [1, 2])
    assert r.depart_min == 6 * 60 + (12 * 60 - avant) and r.arrets[1].attente_min == 0 and r.arrets[1].arrivee_min == 12 * 60
    assert r.retour_min == 12 * 60 + 15 + 20 and r.alertes == []  # le retour au dépôt ne bouge pas : seul le départ est reporté


def test_waiting_is_kept_when_an_earlier_window_closes_first():
    ctx = contexte([cmd(1, fin_min=6 * 60 + 30), cmd(2, debut_min=12 * 60)], positions=[10, 20])
    r = calculer_route(ctx, 1, [1, 2])
    # le 1er arrêt (arrivée 6 h 10, fenêtre close à 6 h 30) permet de partir 20 min plus tard, pas davantage
    assert r.depart_min == 6 * 60 + 20 and r.arrets[0].arrivee_min == 6 * 60 + 30 and r.arrets[1].attente_min == 305 and r.alertes == []


def test_waiting_inside_a_later_rotation_delays_its_exit_from_the_depot():
    ctx = contexte([cmd(1), cmd(2, debut_min=12 * 60)], positions=[10, 20])
    r = calculer_route(ctx, 1, [1, 2], rotations=[1, 2])
    assert [(x.numero, x.depart_min) for x in r.rotations] == [(1, 360), (2, 11 * 60 + 40)]  # rechargé à 7 h 20, il attend au dépôt
    assert r.arrets[1].attente_min == 0 and r.arrets[1].arrivee_min == 12 * 60


def test_maximum_duration_is_measured_without_the_waiting_that_leaving_later_removes():
    ctx = contexte([cmd(1), cmd(2, debut_min=14 * 60)], positions=[10, 10], duree_max=120)
    r = calculer_route(ctx, 1, [1, 2])
    assert r.retour_min - r.depart_min < 120 and r.alertes == []  # sans décalage : 8 heures entre le départ et le retour


def test_changing_order_changes_the_times_and_distance():
    ctx = contexte([cmd(1), cmd(2), cmd(3)], positions=[10, 50, 20])
    droit = calculer_route(ctx, 1, [1, 3, 2])
    zigzag = calculer_route(ctx, 1, [2, 1, 3])
    assert droit.distance_km < zigzag.distance_km and droit.retour_min < zigzag.retour_min


def test_empty_route_costs_nothing():
    r = calculer_route(contexte([cmd(1)]), 1, [])
    assert (r.distance_km, r.trajet_s, r.charge_kg, r.arrets, r.alertes) == (0.0, 0, 0, [], [])


def test_late_arrival_alert_names_order_time_and_delay():
    ctx = contexte([cmd(1, fin_min=6 * 60 + 5)], positions=[30])
    (alerte,) = calculer_route(ctx, 1, [1]).alertes
    assert alerte.type == "retard" and alerte.commande_id == 1 and "R1" in alerte.message and "06:30" in alerte.message and "06:05" in alerte.message
    assert "25 min" in alerte.message


@pytest.mark.parametrize("champ,valeur,cap,mot", [("poids_kg", 900, {"capacite_kg": 800}, "poids"), ("palettes", 5, {"palettes": 4}, "palettes"),
                                                  ("volume_m3", 12.5, {"capacite_m3": 10}, "volume")])
def test_overload_alert(champ, valeur, cap, mot):
    ctx = contexte([cmd(1, **{champ: valeur})], [VehiculeInfo(1, "AA-111-AA", "A", **cap)])
    (alerte,) = calculer_route(ctx, 1, [1]).alertes
    assert alerte.type == "surcharge" and mot in alerte.message and "AA-111-AA" in alerte.message


def test_no_overload_when_capacity_unknown_or_respected():
    ctx = contexte([cmd(1, poids_kg=900)], [VehiculeInfo(1, "AA-111-AA", "A", capacite_kg=900)])
    assert calculer_route(ctx, 1, [1]).alertes == []
    assert calculer_route(contexte([cmd(1, poids_kg=10**6)]), 1, [1]).alertes == []


def test_duration_and_closing_alerts():
    ctx = contexte([cmd(1, service_min=60)], positions=[120], duree_max=200, fermeture=8 * 60)
    types = {a.type for a in calculer_route(ctx, 1, [1]).alertes}
    assert {"duree", "fermeture"} <= types


def test_compatibility_alert_for_frigo_and_adr():
    ctx = contexte([cmd(1, frigo=True, adr=True)], [VehiculeInfo(1, "AA-111-AA", "A", frigo=True)])
    (alerte,) = calculer_route(ctx, 1, [1]).alertes
    assert alerte.type == "incompatible" and "ADR" in alerte.message and "frigo" not in alerte.message


def test_indicators_summary():
    ctx = contexte([cmd(1, poids_kg=500), cmd(2, poids_kg=500, fin_min=6 * 60 + 1)], [VehiculeInfo(1, "A", "A"), VehiculeInfo(2, "B", "A")], positions=[10, 20])
    routes = [calculer_route(ctx, 1, [1, 2]), calculer_route(ctx, 2, [])]
    i = indicateurs(routes, 3, 4000)
    assert i["km"] == 40 and i["nb_tournees"] == 1 and i["remplissage_pct"] == 25 and i["nb_alertes"] == 1 and i["nb_non_affectees"] == 3
    assert indicateurs([calculer_route(ctx, 2, [])], 0, None)["remplissage_pct"] is None


# ---------------------------------------------------------------- Rotations (plusieurs sorties du dépôt dans la journée)


def test_second_rotation_returns_to_depot_reloads_and_leaves_again():
    from app.planning import normaliser_rotations  # noqa: F401
    ctx = contexte([cmd(1, palettes=4), cmd(2, palettes=6)], positions=[10, 20])
    r = calculer_route(ctx, 1, [1, 2], rotations=[1, 2])
    a, b = r.arrets
    # 6 h : trajet 10, service 15, retour 10 -> 6 h 35 ; rechargement 45 -> 7 h 20 ; trajet 20 -> 7 h 40 ; service 15 ; retour 20 -> 8 h 15
    assert (r.depart_min, a.arrivee_min, a.depart_min) == (360, 370, 385)
    assert (b.arrivee_min, b.depart_min, r.retour_min) == (460, 475, 495)
    assert [(x.numero, x.depart_min, x.retour_min, x.charge_palettes) for x in r.rotations] == [(1, 360, 395, 4), (2, 440, 495, 6)]
    assert (r.distance_km, r.trajet_s, r.charge_palettes) == (60, 3600, 10) and (a.rotation, b.rotation) == (1, 2)


def test_loading_time_is_a_setting():
    ctx = contexte([cmd(1), cmd(2)], positions=[10, 20])
    ctx.rechargement_min = 90
    assert calculer_route(ctx, 1, [1, 2], rotations=[1, 2]).arrets[1].arrivee_min == 460 + 45


def test_without_rotations_nothing_changes():
    ctx = contexte([cmd(1, service_min=30), cmd(2, service_min=15)], positions=[10, 20])
    assert calculer_route(ctx, 1, [1, 2]).retour_min == calculer_route(ctx, 1, [1, 2], rotations=[1, 1]).retour_min


def test_overload_is_checked_per_rotation_not_on_the_day_total():
    camion = VehiculeInfo(1, "AA-111-AA", "A", palettes=10)
    ctx = contexte([cmd(1, palettes=8), cmd(2, palettes=8)], vehicules=[camion], positions=[10, 20])
    assert calculer_route(ctx, 1, [1, 2], rotations=[1, 2]).alertes == []
    (alerte,) = calculer_route(ctx, 1, [1, 2], rotations=[1, 1]).alertes
    assert alerte.type == "surcharge" and "16 palettes pour 10" in alerte.message
    sur = calculer_route(contexte([cmd(1, palettes=12), cmd(2, palettes=2)], vehicules=[camion], positions=[10, 20]), 1, [1, 2], rotations=[1, 2])
    assert [a.type for a in sur.alertes] == ["surcharge"] and "rotation 1" in sur.alertes[0].message


def test_max_duration_applies_to_each_rotation():
    ctx = contexte([cmd(1, service_min=40), cmd(2, service_min=40)], positions=[10, 10], duree_max=60)
    assert [a.type for a in calculer_route(ctx, 1, [1, 2], rotations=[1, 1]).alertes] == ["duree"]  # 10 + 40 + 0 + 40 + 10 = 100 min
    assert calculer_route(ctx, 1, [1, 2], rotations=[1, 2]).alertes == []  # 60 min chacune


def test_daily_driving_adds_up_over_rotations_and_breaks_are_inserted():
    ctx = contexte([cmd(1), cmd(2)], positions=[150, 150])
    r = calculer_route(ctx, 1, [1, 2], rotations=[1, 2])
    assert r.conduite_min == 600 and len(r.pauses) == 2  # le chargement n'est pas une pause : 4 h 30 de conduite continue sont vite atteintes
    assert [a.type for a in r.alertes] == ["extension"]  # 10 h pile : une extension à 10 h, pas une infraction


def test_return_after_closing_is_reported_once_for_the_whole_day():
    ctx = contexte([cmd(1), cmd(2)], positions=[10, 20], fermeture=8 * 60)
    assert [a.type for a in calculer_route(ctx, 1, [1, 2], rotations=[1, 2]).alertes] == ["fermeture"]


@pytest.mark.parametrize("entree,n,attendu", [(None, 3, [1, 1, 1]), ([2, 2, 5], 3, [1, 1, 2]), ([3, 1], 2, [1, 1]), ([1], 3, [1, 1, 1]), ([1, 2], 4, [1, 2, 2, 2]), ([0, 1], 2, [1, 1])])
def test_rotation_numbers_are_normalised(entree, n, attendu):
    from app.planning import normaliser_rotations
    assert normaliser_rotations(entree, n) == attendu


def test_live_simulation_returns_to_depot_before_the_next_rotation():
    from app.planning import simuler_depuis
    ctx = contexte([cmd(1), cmd(2)], positions=[10, 20])
    # Camion à 10 km (position du 1er arrêt) à 7 h, rotation 1 ; reste l'arrêt 2 en rotation 2 :
    # retour au dépôt 10 min -> 7 h 10, rechargement 45 -> 7 h 55, trajet 20 -> 8 h 15 (arrivée), service 15, retour 20 -> 8 h 50
    s = simuler_depuis(ctx, 1, [2], depuis_ligne=1, depuis_min=7 * 60, rotations=[2], rotation_depuis=1)
    assert s.arrets[0].arrivee_min == 8 * 60 + 15 and s.retour_min == 8 * 60 + 50 and s.distance_km == 10 + 20 + 20


def test_live_simulation_without_rotation_change_goes_straight_on():
    from app.planning import simuler_depuis
    ctx = contexte([cmd(1), cmd(2)], positions=[10, 20])
    s = simuler_depuis(ctx, 1, [2], depuis_ligne=1, depuis_min=7 * 60, rotations=[2], rotation_depuis=2)
    assert s.arrets[0].arrivee_min == 7 * 60 + 10 and s.distance_km == 10 + 20


def test_live_simulation_does_not_reload_twice_for_a_truck_still_at_the_depot():
    from app.planning import simuler_depuis
    ctx = contexte([cmd(1)], positions=[10])
    s = simuler_depuis(ctx, 1, [1], depuis_ligne=0, depuis_min=6 * 60, rotations=[2], rotation_depuis=1)
    assert s.arrets[0].arrivee_min == 6 * 60 + 10
