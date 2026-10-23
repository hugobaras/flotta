"""Cas chiffrés du module de temps de conduite (règlement CE 561/2006). Les durées sont en minutes ; h(x) = x heures."""
import pytest

from app import regulations as r
from app.regulations import CONDUITE, DISPONIBILITE, REPOS, TRAVAIL, Activite, analyser, restant

SEMAINE = r.constantes.SEMAINE


def h(x):
    return int(round(x * 60))


def suite(*segments, debut=6 * 60):
    """segments = (type, durée) bout à bout depuis `debut` (lundi 06:00 par défaut)."""
    t, sortie = debut, []
    for type_, duree in segments:
        sortie.append(Activite(type_, t, t + duree))
        t += duree
    return sortie


def codes(activites):
    return [i.code for i in analyser(activites).infractions]


def journee(conduite, debut, repos=h(11), travail=0):
    """Une journée valable : conduite avec pauses de 45 min toutes les 4 h 30, puis un repos."""
    segs, reste = [], conduite
    while reste > 0:
        tranche = min(reste, h(4.5))
        segs.append((CONDUITE, tranche))
        reste -= tranche
        if reste > 0:
            segs.append((REPOS, 45))
    if travail:
        segs.append((TRAVAIL, travail))
    segs.append((REPOS, repos))
    return suite(*segs, debut=debut)


def semaine_type(jours_minutes, lundi=0, repos=h(11), debut=None, travail=0):
    """Journées enchaînées (chacune se termine par son repos). Par défaut : première journée le lundi à 06:00."""
    activites, t = [], lundi + 6 * 60 if debut is None else debut
    for m in jours_minutes:
        a = journee(m, t, repos, travail)
        activites += a
        t = a[-1].fin
    return activites


# ---------------------------------------------------------------- Art. 7 : pauses


def test_exactly_4h30_of_driving_then_break_is_fine():
    assert codes(suite((CONDUITE, h(4.5)), (REPOS, 45), (CONDUITE, h(4.5)))) == []


def test_one_minute_over_4h30_is_an_infraction_dated_at_the_limit():
    (i,) = analyser(suite((CONDUITE, h(4.5) + 1))).infractions
    assert i.code == "PAUSE_MANQUANTE" and i.debut == 6 * 60 + h(4.5)


def test_a_44_minute_rest_is_not_a_full_break():
    assert "PAUSE_MANQUANTE" in codes(suite((CONDUITE, h(4.5)), (REPOS, 44), (CONDUITE, 1)))


def test_split_break_15_then_30_inside_the_period_is_valid():
    assert codes(suite((CONDUITE, h(2)), (REPOS, 15), (CONDUITE, h(2.5)), (REPOS, 30), (CONDUITE, h(4.5)))) == []


def test_split_break_in_the_wrong_order_is_invalid():
    assert "PAUSE_MANQUANTE" in codes(suite((CONDUITE, h(2)), (REPOS, 30), (TRAVAIL, 5), (REPOS, 15), (CONDUITE, h(3))))


def test_first_part_15_minutes_does_not_restart_the_4h30_count():
    assert "PAUSE_MANQUANTE" in codes(suite((CONDUITE, h(4.5)), (REPOS, 15), (CONDUITE, 10)))


def test_other_work_is_not_a_break():
    assert "PAUSE_MANQUANTE" in codes(suite((CONDUITE, h(3)), (TRAVAIL, 60), (CONDUITE, h(2))))


def test_availability_is_not_a_break_either():
    assert "PAUSE_MANQUANTE" in codes(suite((CONDUITE, h(3)), (DISPONIBILITE, 60), (CONDUITE, h(2))))


def test_a_gap_in_the_record_counts_as_rest():
    a = [Activite(CONDUITE, 360, 360 + h(4)), Activite(CONDUITE, 360 + h(4) + 50, 360 + h(8) + 50)]
    assert codes(a) == []


def test_short_interruptions_under_15_minutes_do_not_count():
    assert "PAUSE_MANQUANTE" in codes(suite((CONDUITE, h(3)), (REPOS, 14), (CONDUITE, h(2))))


def test_long_driving_without_break_is_reported_once():
    assert codes(suite((CONDUITE, h(10)))).count("PAUSE_MANQUANTE") == 1


def test_overlapping_activities_are_refused():
    with pytest.raises(ValueError):
        analyser([Activite(CONDUITE, 0, 100), Activite(TRAVAIL, 50, 150)])


def test_unknown_type_and_negative_duration_are_refused():
    with pytest.raises(ValueError):
        Activite("sieste", 0, 10)
    with pytest.raises(ValueError):
        Activite(CONDUITE, 10, 0)


# ---------------------------------------------------------------- Art. 6 : conduite journalière et hebdomadaire


def test_9h_of_driving_is_normal():
    a = analyser(journee(h(9), 6 * 60))
    assert a.infractions == [] and a.jours[0].conduite == h(9)


def test_9h30_uses_an_extension_but_is_allowed_once():
    assert codes(journee(h(9.5), 6 * 60)) == []


def test_exactly_10h_is_allowed_and_one_minute_more_is_not():
    assert "CONDUITE_JOURNALIERE" not in codes(journee(h(10), 6 * 60))
    assert "CONDUITE_JOURNALIERE" in codes(journee(h(10) + 1, 6 * 60))


def test_two_10h_days_are_allowed_a_third_is_not():
    deux = semaine_type([h(10), h(10)])
    trois = semaine_type([h(10), h(10), h(10)])
    assert "EXTENSION_10H_EXCEDEE" not in codes(deux)
    assert codes(trois).count("EXTENSION_10H_EXCEDEE") == 1


def test_extensions_are_counted_per_calendar_week():
    # Deux jours de 10 h en fin de semaine, deux autres la semaine suivante : aucun dépassement.
    a = semaine_type([h(10), h(10)], lundi=0) + semaine_type([h(10), h(10)], lundi=SEMAINE)
    assert "EXTENSION_10H_EXCEDEE" not in codes(a)


def test_weekly_driving_limit_56h():
    jours = [h(9)] * 6 + [h(2)]
    assert "CONDUITE_HEBDOMADAIRE" not in codes(semaine_type(jours))  # 56 h pile
    assert "CONDUITE_HEBDOMADAIRE" in codes(semaine_type(jours[:-1] + [h(2) + 1]))


def test_two_week_limit_90h():
    s1 = semaine_type([h(9)] * 6 + [h(2)], lundi=0)  # 56 h
    ok = s1 + semaine_type([h(9)] * 3 + [h(7)], lundi=SEMAINE)  # 34 h, total 90 h
    trop = s1 + semaine_type([h(9)] * 3 + [h(7) + 1], lundi=SEMAINE)
    assert "CONDUITE_BIHEBDOMADAIRE" not in codes(ok)
    assert "CONDUITE_BIHEBDOMADAIRE" in codes(trop)


def test_driving_across_the_week_boundary_is_split_between_the_two_weeks():
    a = [Activite(CONDUITE, SEMAINE - 60, SEMAINE + 60)]
    assert analyser(a).conduite_par_semaine == {0: 60, 1: 60}


# ---------------------------------------------------------------- Art. 8 : repos


def test_11h_daily_rest_is_normal():
    veille = journee(h(8), 6 * 60)
    a = analyser(veille + suite((CONDUITE, 60), debut=veille[-1].fin))
    assert a.jours[0].type_repos == "normal" and a.infractions == []


def test_daily_rest_taken_too_late_is_flagged():
    a = suite((TRAVAIL, h(15)), (REPOS, h(11)), (CONDUITE, 30))
    assert "REPOS_JOURNALIER_TARDIF" in codes(a)


def test_a_9h_reduced_rest_is_classified_reduced_and_limited_to_three():
    quatre = semaine_type([h(8)] * 5, repos=h(9))
    a = analyser(quatre)
    assert [j.type_repos for j in a.jours if j.repos_apres] == ["reduit"] * 5
    assert [i.code for i in a.infractions].count("REPOS_REDUIT_EXCEDE") == 2  # le 4e et le 5e
    assert "REPOS_REDUIT_EXCEDE" not in codes(semaine_type([h(8)] * 3, repos=h(9)))


def test_split_daily_rest_3h_plus_9h_counts_as_a_regular_rest():
    a = analyser(suite((CONDUITE, h(4)), (REPOS, 45), (CONDUITE, h(3)), (REPOS, h(3)), (TRAVAIL, h(2)), (REPOS, h(9)), (CONDUITE, 30)))
    assert a.jours[0].type_repos == "fractionne" and "REPOS_REDUIT_EXCEDE" not in [i.code for i in a.infractions]


def test_no_daily_rest_within_24h_is_reported():
    a = suite((TRAVAIL, h(10)), (REPOS, h(5)), (TRAVAIL, h(10)))
    assert "REPOS_JOURNALIER_MANQUANT" in codes(a)


def test_weekly_rest_regular_and_reduced():
    normal = analyser(journee(h(8), 6 * 60, repos=h(45)))
    assert normal.jours[0].type_repos == "hebdomadaire" and normal.notes == []
    reduit = analyser(journee(h(8), 6 * 60, repos=h(30)))
    assert reduit.jours[0].type_repos == "hebdomadaire" and any("réduit" in n for n in reduit.notes)


def test_a_20h_rest_is_a_daily_rest_not_a_weekly_one():
    assert analyser(journee(h(8), 6 * 60, repos=h(20))).jours[0].type_repos == "normal"


def test_weekly_rest_must_start_within_six_24h_periods():
    repos_hebdo = semaine_type([h(8)], repos=h(45))
    sept_jours = semaine_type([h(8)] * 7, debut=repos_hebdo[-1].fin, travail=h(3))  # 7 x 22 h 45, sans repos de 24 h
    assert "REPOS_HEBDO_MANQUANT" in codes(repos_hebdo + sept_jours)
    six_jours = semaine_type([h(8)] * 6, debut=repos_hebdo[-1].fin, travail=h(3))  # 6 x 22 h 45 = 136 h : dans la limite de 144 h
    assert "REPOS_HEBDO_MANQUANT" not in codes(repos_hebdo + six_jours)


# ---------------------------------------------------------------- Temps restants


def test_remaining_times_for_a_rested_driver_with_no_history():
    x = restant([], 6 * 60)
    assert (x.conduite_continue, x.pause_necessaire, x.conduite_jour, x.conduite_jour_normale) == (270, 45, 600, 540)
    assert x.extensions_restantes == 2 and x.conduite_semaine == 3360 and x.debut_possible == 6 * 60


def test_remaining_after_three_hours_of_driving():
    x = restant(suite((CONDUITE, h(3))), 6 * 60 + h(3))
    assert x.conduite_continue == 90 and x.conduite_jour == 600 - 180 and x.conduite_jour_normale == 540 - 180


def test_remaining_knows_the_first_part_of_a_split_break():
    x = restant(suite((CONDUITE, h(2)), (REPOS, 15)), 6 * 60 + h(2) + 15)
    assert x.conduite_continue == 270 - 120 and x.pause_necessaire == 30


def test_remaining_after_a_full_break_restarts_the_count():
    x = restant(suite((CONDUITE, h(4)), (REPOS, 45)), 6 * 60 + h(4) + 45)
    assert x.conduite_continue == 270 and x.conduite_jour == 600 - 240


def test_extensions_used_earlier_in_the_week_remove_the_10h_allowance():
    historique = semaine_type([h(10), h(10)])
    x = restant(historique, historique[-1].fin)
    assert x.extensions_restantes == 0 and x.conduite_jour == 540
    un = semaine_type([h(10)])
    assert restant(un, un[-1].fin).extensions_restantes == 1


def test_weekly_remaining_takes_the_two_week_ceiling_into_account():
    precedente = semaine_type([h(9)] * 5 + [h(8)], lundi=0)  # 53 h
    maintenant = SEMAINE + 6 * 60
    assert restant(precedente, maintenant).conduite_semaine == min(3360, 5400 - 53 * 60)
    lourde = semaine_type([h(9)] * 6 + [h(2)], lundi=0)  # 56 h
    assert restant(lourde, maintenant).conduite_semaine == 5400 - 3360


def test_earliest_restart_after_an_incomplete_rest():
    fin_travail = 6 * 60 + h(10)
    x = restant(suite((TRAVAIL, h(10))), fin_travail + h(5))
    assert x.debut_possible == fin_travail + h(11) and x.debut_possible_reduit == fin_travail + h(9)
    y = restant(suite((TRAVAIL, h(10))), fin_travail + h(12))
    assert y.debut_possible == fin_travail + h(12)


def test_remaining_ignores_activities_after_now():
    x = restant(suite((CONDUITE, h(3))), 6 * 60 + h(1))
    assert x.conduite_continue == 270 - 60


# ---------------------------------------------------------------- Planification : pauses insérées


def test_no_break_needed_up_to_4h30():
    p = r.conduire(r.demarrer(0), h(4.5))
    assert p.pauses == [] and p.t == h(4.5) and p.conduite_totale == h(4.5)


def test_one_break_inserted_exactly_when_the_limit_is_reached():
    p = r.conduire(r.demarrer(0), h(4.5) + 1)
    assert p.pauses == [(h(4.5), h(4.5) + 45)] and p.t == h(4.5) + 45 + 1


def test_ten_hours_of_driving_need_two_breaks():
    p = r.conduire(r.demarrer(0), h(10))
    assert p.pauses == [(270, 315), (585, 630)] and p.t == h(10) + 90 and p.conduite_totale == h(10)


def test_work_and_waiting_do_not_restart_the_count():
    p = r.demarrer(0)
    r.conduire(p, 200)
    r.travailler(p, 120)
    r.attendre(p, 60)
    r.conduire(p, 100)
    assert len(p.pauses) == 1 and p.pauses[0][0] == 200 + 120 + 60 + 70  # pause après les 70 min qui complètent 4 h 30


def test_initial_counter_is_honoured_and_split_break_shortens_the_next_pause():
    p = r.conduire(r.demarrer(0, r.Chrono(conduite=200)), 100)
    assert p.pauses == [(70, 115)]
    p = r.conduire(r.demarrer(0, r.Chrono(conduite=200, partie1=True)), 100)
    assert p.pauses == [(70, 100)]  # 30 min suffisent : la première partie est déjà prise


def test_planned_activities_are_contiguous_and_pass_the_analyser():
    p = r.demarrer(360)
    r.conduire(p, h(3))
    r.travailler(p, 45)
    r.conduire(p, h(3))
    r.attendre(p, 20)
    r.travailler(p, 30)
    r.conduire(p, h(3.5))
    for a, b in zip(p.activites, p.activites[1:]):
        assert a.fin == b.debut
    assert [i.code for i in analyser(p.activites).infractions] == []  # le planificateur ne produit jamais de PAUSE_MANQUANTE
    assert p.chrono.infractions == []
