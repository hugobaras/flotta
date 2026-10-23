import math
import random
import time

import pytest

from app.optimisation import (INJOIGNABLE_S, CommandeOpt, Probleme, VehiculeOpt, optimiser)


def ligne(*positions_km):
    """Matrice des durées pour des points alignés (km depuis le dépôt) : 60 s par kilomètre, soit 60 km/h."""
    pts = [0, *positions_km]
    return [[int(abs(a - b) * 60) for b in pts] for a in pts]


def pb(commandes, vehicules=None, positions=None, **kw):
    positions = positions or [10 * (i + 1) for i in range(len(commandes))]
    vehicules = [VehiculeOpt(1, "A")] if vehicules is None else vehicules
    return Probleme(vehicules=vehicules, commandes=commandes, matrices=kw.pop("matrices", None) or {"A": ligne(*positions)},
                    temps_calcul_s=kw.pop("temps_calcul_s", 1), **kw)


def servies(s):
    return sorted(a.commande_id for r in s.routes for a in r.arrets)


def raisons(s):
    return dict(s.non_affectees)


def test_every_order_served_once_when_everything_fits():
    s = optimiser(pb([CommandeOpt(i, poids_kg=100) for i in range(1, 6)]))
    assert servies(s) == [1, 2, 3, 4, 5] and s.non_affectees == []


def test_vehicle_capacity_splits_orders_across_vehicles():
    cmds = [CommandeOpt(i, poids_kg=600) for i in range(1, 5)]  # 2400 kg, 2 camions de 1300 kg
    vehs = [VehiculeOpt(1, "A", capacite_kg=1300), VehiculeOpt(2, "A", capacite_kg=1300)]
    s = optimiser(pb(cmds, vehs))
    assert servies(s) == [1, 2, 3, 4] and len(s.routes) == 2
    for r in s.routes:
        assert len(r.arrets) == 2  # jamais 3 x 600 kg dans 1300 kg


@pytest.mark.parametrize("champ,valeur,cap", [("poids_kg", 900, {"capacite_kg": 800}), ("palettes", 5, {"palettes": 4}), ("volume_m3", 12, {"capacite_m3": 10})])
def test_order_larger_than_any_vehicle_is_explained(champ, valeur, cap):
    s = optimiser(pb([CommandeOpt(1, **{champ: valeur})], [VehiculeOpt(1, "A", **cap)]))
    assert servies(s) == [] and raisons(s)[1].startswith("Capacité")


def test_total_fleet_capacity_exceeded_leaves_orders_with_the_right_reason():
    cmds = [CommandeOpt(i, poids_kg=500) for i in range(1, 5)]
    s = optimiser(pb(cmds, [VehiculeOpt(1, "A", capacite_kg=1000)]))
    assert len(servies(s)) == 2 and len(s.non_affectees) == 2
    assert all("Capacité totale" in r for r in raisons(s).values())


def test_time_windows_are_respected_and_waiting_is_reported():
    cmds = [CommandeOpt(1, debut_min=10 * 60, fin_min=11 * 60), CommandeOpt(2, debut_min=7 * 60, fin_min=8 * 60)]
    s = optimiser(pb(cmds, positions=[10, 20], ouverture_min=6 * 60))
    assert servies(s) == [1, 2]
    arrets = {a.commande_id: a for r in s.routes for a in r.arrets}
    assert 10 * 60 <= arrets[1].arrivee_min <= 11 * 60 and 7 * 60 <= arrets[2].arrivee_min <= 8 * 60
    assert arrets[2].arrivee_min < arrets[1].arrivee_min  # la fenêtre du matin passe en premier


def test_service_time_is_added_between_stops():
    s = optimiser(pb([CommandeOpt(1, service_min=30), CommandeOpt(2, service_min=45)], positions=[10, 20], pauses=False))
    a, b = s.routes[0].arrets
    assert abs((b.arrivee_min - a.depart_min) - 10) < 0.01  # 10 km à 60 km/h = 10 min de trajet
    assert abs((a.depart_min - a.arrivee_min) - (30 if a.commande_id == 1 else 45)) < 0.01


def test_route_is_consistent_with_depot_hours():
    s = optimiser(pb([CommandeOpt(i) for i in range(1, 6)], ouverture_min=7 * 60, fermeture_min=18 * 60))
    r = s.routes[0]
    assert r.depart_min >= 7 * 60 and r.retour_min <= 18 * 60
    assert all(x.arrivee_min < y.arrivee_min for x, y in zip(r.arrets, r.arrets[1:]))
    assert r.trajet_s > 0 and r.arrets[0].arrivee_min >= r.depart_min


def test_unreachable_window_is_explained():
    s = optimiser(pb([CommandeOpt(1, fin_min=6 * 60 + 5)], positions=[30], ouverture_min=6 * 60))  # 30 min de route, fenêtre close à 6h05
    assert servies(s) == [] and "Fenêtre horaire inaccessible" in raisons(s)[1]


def test_return_after_depot_closing_is_explained():
    s = optimiser(pb([CommandeOpt(1, service_min=120)], positions=[60], ouverture_min=6 * 60, fermeture_min=8 * 60 + 30))
    assert servies(s) == [] and "fermeture" in raisons(s)[1]


def test_max_route_duration_is_a_hard_limit():
    cmds = [CommandeOpt(i, service_min=20) for i in range(1, 9)]
    vehs = [VehiculeOpt(1, "A"), VehiculeOpt(2, "A")]
    s = optimiser(pb(cmds, vehs, positions=[15, 20, 25, 30, 35, 40, 45, 50], duree_max_min=240))
    for r in s.routes:
        assert r.retour_min - r.depart_min <= 240 + 0.01
    assert len(servies(s)) + len(s.non_affectees) == 8


def test_order_longer_than_max_duration_is_explained():
    s = optimiser(pb([CommandeOpt(1)], positions=[200], duree_max_min=180))  # 400 min d'aller-retour
    assert servies(s) == [] and "Durée maximale" in raisons(s)[1]


def test_frigo_and_adr_orders_only_on_compatible_vehicles():
    cmds = [CommandeOpt(1, frigo=True), CommandeOpt(2, adr=True), CommandeOpt(3)]
    vehs = [VehiculeOpt(1, "A", frigo=True), VehiculeOpt(2, "A", adr=True), VehiculeOpt(3, "A")]
    s = optimiser(pb(cmds, vehs))
    place = {a.commande_id: r.vehicule_id for r in s.routes for a in r.arrets}
    assert place[1] == 1 and place[2] == 2 and 3 in place


def test_no_compatible_vehicle_is_explained():
    s = optimiser(pb([CommandeOpt(1, frigo=True, adr=True)], [VehiculeOpt(1, "A", frigo=True), VehiculeOpt(2, "A", adr=True)]))
    assert servies(s) == [] and raisons(s)[1] == "Aucun véhicule compatible (frigo et ADR requis)"


def test_unreachable_address_is_explained():
    m = ligne(10, 20)
    m[0][2], m[2][0] = INJOIGNABLE_S, INJOIGNABLE_S
    s = optimiser(pb([CommandeOpt(1), CommandeOpt(2)], matrices={"A": m}))
    assert servies(s) == [1] and "inaccessible" in raisons(s)[2]


def test_each_vehicle_uses_the_matrix_of_its_profile():
    lent = [[t * 3 for t in row] for row in ligne(10)]
    s = optimiser(pb([CommandeOpt(1)], [VehiculeOpt(1, "lent"), VehiculeOpt(2, "rapide")], matrices={"lent": lent, "rapide": ligne(10)}))
    assert [r.vehicule_id for r in s.routes] == [2]


def test_no_vehicle_means_everything_is_unassigned():
    s = optimiser(pb([CommandeOpt(1), CommandeOpt(2)], vehicules=[]))
    assert s.routes == [] and set(raisons(s).values()) == {"Aucun véhicule disponible"}


def positions_aleatoires(n, graine=7):
    random.seed(graine)
    return [(47.2184 + random.uniform(-0.4, 0.4), -1.5536 + random.uniform(-0.6, 0.6)) for _ in range(n)]


def matrice_haversine(pts, vitesse_kmh=60, detour=1.3):
    def d(a, b):
        (la1, lo1), (la2, lo2) = a, b
        x = math.sin(math.radians(la1)) * math.sin(math.radians(la2)) + math.cos(math.radians(la1)) * math.cos(math.radians(la2)) * math.cos(math.radians(lo1 - lo2))
        return 6371 * math.acos(min(1.0, x)) * detour
    return [[0 if i == j else int(d(pts[i], pts[j]) / vitesse_kmh * 3600) for j in range(len(pts))] for i in range(len(pts))]


def probleme_100_commandes(temps_calcul_s):
    random.seed(3)
    pts = [(47.2184, -1.5536)] + positions_aleatoires(100)
    cmds = [CommandeOpt(i + 1, poids_kg=random.randint(100, 1200), palettes=random.randint(1, 4), volume_m3=random.uniform(1, 8),
                        debut_min=random.choice([None, 8 * 60, 10 * 60]), fin_min=random.choice([None, 12 * 60, 17 * 60]), service_min=15)
            for i in range(100)]
    vehs = [VehiculeOpt(i + 1, "A", capacite_kg=12000, palettes=33, capacite_m3=80) for i in range(8)]
    return Probleme(vehs, cmds, {"A": matrice_haversine(pts)}, temps_calcul_s=temps_calcul_s)


def test_100_orders_8_trucks_in_under_60_seconds_with_every_order_accounted_for():
    debut = time.time()
    s = optimiser(probleme_100_commandes(10))
    assert time.time() - debut < 60
    assert len(servies(s)) + len(s.non_affectees) == 100 and len(servies(s)) == len(set(servies(s)))
    assert all(raison for _, raison in s.non_affectees)
    for r in s.routes:
        assert r.retour_min - r.depart_min <= 600 + 0.01


def test_calculation_time_parameter_is_a_maximum():
    debut = time.time()
    optimiser(probleme_100_commandes(1))
    assert time.time() - debut < 6


# --- Temps de conduite réglementaires ---


def test_vehicle_driving_cap_is_a_hard_limit_and_explained():
    cmds = [CommandeOpt(i, service_min=5) for i in range(1, 5)]
    s = optimiser(pb(cmds, [VehiculeOpt(1, "A", conduite_max_min=150)], positions=[30, 60, 90, 120], pauses=False, duree_max_min=900))
    for r in s.routes:
        assert r.trajet_s <= 150 * 60
    assert len(servies(s)) < 4 and all("conduite" in x.lower() or "Capacité" in x for x in raisons(s).values())


def test_order_beyond_the_driving_cap_is_reported_with_the_driving_reason():
    s = optimiser(pb([CommandeOpt(1)], [VehiculeOpt(1, "A", conduite_max_min=90)], positions=[60]))  # 2 h d'aller-retour pour 1 h 30 permises
    assert servies(s) == [] and raisons(s)[1].startswith("Temps de conduite")


def test_earliest_start_of_a_driver_delays_the_route():
    s = optimiser(pb([CommandeOpt(1)], [VehiculeOpt(1, "A", debut_min=9 * 60)], positions=[10], ouverture_min=6 * 60))
    assert s.routes[0].depart_min >= 9 * 60 - 1e-6 and s.routes[0].arrets[0].arrivee_min >= 9 * 60 + 10


def test_break_time_is_counted_when_checking_a_time_window():
    # 5 h de route à l'aller : une pause de 45 min est obligatoire, l'arrivée au plus tôt est donc 5 h 45 après l'ouverture
    s = optimiser(pb([CommandeOpt(1, fin_min=6 * 60 + 5 * 60 + 30)], [VehiculeOpt(1, "A", conduite_max_min=700)], positions=[300],
                     ouverture_min=6 * 60, fermeture_min=23 * 60, duree_max_min=900))
    assert servies(s) == [] and "Fenêtre horaire inaccessible" in raisons(s)[1]
    s = optimiser(pb([CommandeOpt(1, fin_min=6 * 60 + 5 * 60 + 50)], [VehiculeOpt(1, "A", conduite_max_min=700)], positions=[300],
                     ouverture_min=6 * 60, fermeture_min=23 * 60, duree_max_min=900))
    assert servies(s) == [1]


def test_pessimistic_break_model_never_underestimates_real_arrival_times():
    """Garantie de cohérence : avec les pauses réelles placées au dernier moment, aucun arrêt n'est atteint plus tard que prévu."""
    from app import regulations as reg
    cmds = [CommandeOpt(i, service_min=20) for i in range(1, 8)]
    positions = [60, 140, 200, 270, 330, 370, 420]
    m = ligne(*positions)
    s = optimiser(pb(cmds, [VehiculeOpt(1, "A", conduite_max_min=700)], positions=positions, matrices={"A": m}, duree_max_min=900,
                     fermeture_min=23 * 60, temps_calcul_s=3))
    for r in s.routes:
        p, prec = reg.demarrer(r.depart_min), 0
        for a in r.arrets:
            ligne_i = a.commande_id
            reg.conduire(p, m[prec][ligne_i] / 60)
            reel = p.t
            assert reel <= a.arrivee_min + 1e-6, (a.commande_id, reel, a.arrivee_min)
            reg.travailler(p, 20)
            prec = ligne_i
        assert p.chrono.infractions == []


def test_total_driving_of_every_route_respects_each_vehicle_cap():
    s = optimiser(probleme_100_commandes(5))
    for r in s.routes:
        assert r.trajet_s <= 540 * 60 + 1


# ---------------------------------------------------------------- Rotations


def trois_commandes_de_8_palettes():
    return [CommandeOpt(i, palettes=8) for i in (1, 2, 3)]


def test_one_truck_serves_everything_with_three_rotations_where_one_cannot():
    veh = [VehiculeOpt(1, "A", palettes=10)]  # 8 palettes par commande : une seule commande par rotation
    seule = optimiser(pb(trois_commandes_de_8_palettes(), veh, positions=[10, 10, 10], rotations_max=1))
    assert len(servies(seule)) == 1 and len(seule.non_affectees) == 2
    s = optimiser(pb(trois_commandes_de_8_palettes(), veh, positions=[10, 10, 10], rotations_max=3))
    assert servies(s) == [1, 2, 3] and s.non_affectees == []
    (route,) = s.routes
    assert [a.rotation for a in route.arrets] == [1, 2, 3]


def test_rotations_are_capped_by_the_setting():
    s = optimiser(pb(trois_commandes_de_8_palettes(), [VehiculeOpt(1, "A", palettes=10)], positions=[10, 10, 10], rotations_max=2))
    assert len(servies(s)) == 2 and len(s.non_affectees) == 1


def test_next_rotation_starts_after_return_and_loading():
    s = optimiser(pb(trois_commandes_de_8_palettes()[:2], [VehiculeOpt(1, "A", palettes=10)], positions=[10, 10], rotations_max=2, rechargement_min=45))
    a, b = s.routes[0].arrets
    assert (a.rotation, b.rotation) == (1, 2)
    # fin de service de la 1re commande + 10 min de retour + 45 min de chargement + 10 min d'aller = arrivée minimale à la 2e
    assert b.arrivee_min >= a.depart_min + 10 + 45 + 10 - 1e-6


def test_longer_loading_time_pushes_the_second_rotation_later():
    court = optimiser(pb(trois_commandes_de_8_palettes()[:2], [VehiculeOpt(1, "A", palettes=10)], positions=[10, 10], rotations_max=2, rechargement_min=30))
    long = optimiser(pb(trois_commandes_de_8_palettes()[:2], [VehiculeOpt(1, "A", palettes=10)], positions=[10, 10], rotations_max=2, rechargement_min=120))
    assert long.routes[0].retour_min - court.routes[0].retour_min >= 90 - 1e-6


def test_daily_driving_limit_is_shared_by_all_rotations_of_a_truck():
    # aller-retour de 40 min par commande : deux rotations = 80 min, trois = 120 min > 100 min de conduite autorisée
    veh = [VehiculeOpt(1, "A", palettes=10, conduite_max_min=100)]
    s = optimiser(pb(trois_commandes_de_8_palettes(), veh, positions=[20, 20, 20], rotations_max=3, pauses=False))
    assert len(servies(s)) == 2 and len(s.non_affectees) == 1


def test_closing_time_limits_the_number_of_rotations():
    s = optimiser(pb(trois_commandes_de_8_palettes(), [VehiculeOpt(1, "A", palettes=10)], positions=[10, 10, 10], rotations_max=3,
                     ouverture_min=6 * 60, fermeture_min=6 * 60 + 150))
    # 1re rotation : 35 min ; chargement 45 ; 2e rotation : 35 min -> 115 min ; une 3e dépasserait 150 min
    assert len(servies(s)) == 2


def test_two_trucks_use_rotations_independently():
    cmds = [CommandeOpt(i, palettes=8) for i in range(1, 5)]
    vehs = [VehiculeOpt(1, "A", palettes=10), VehiculeOpt(2, "A", palettes=10)]
    s = optimiser(pb(cmds, vehs, positions=[10, 10, 10, 10], rotations_max=2))
    assert servies(s) == [1, 2, 3, 4] and sorted(len({a.rotation for a in r.arrets}) for r in s.routes) == [2, 2]


def test_reason_explains_that_no_truck_can_leave_again():
    # 3 x 8 palettes pour un camion de 10 et un dépôt qui ferme tôt : la 3e commande reste de côté, faute de camion qui puisse repartir
    s = optimiser(pb(trois_commandes_de_8_palettes(), [VehiculeOpt(1, "A", palettes=10)], positions=[10, 10, 10], rotations_max=3,
                     ouverture_min=6 * 60, fermeture_min=6 * 60 + 150))
    assert len(s.non_affectees) == 1 and "Aucun camion ne peut repartir" in raisons(s)[s.non_affectees[0][0]]


def test_a_single_rotation_gives_the_same_result_as_before():
    cmds = [CommandeOpt(i, poids_kg=100) for i in range(1, 6)]
    avant = optimiser(pb(cmds))
    apres = optimiser(pb(cmds, rotations_max=1))
    assert [(a.commande_id, a.rotation) for a in apres.routes[0].arrets] == [(a.commande_id, 1) for a in avant.routes[0].arrets]
