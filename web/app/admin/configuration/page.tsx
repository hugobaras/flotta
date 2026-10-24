"use client";

import { Panneau } from "../panneau";
import Flotte from "../_sections/flotte";
import Conducteurs from "../_sections/conducteurs";
import Depots from "../_sections/depots";
import Checklists from "../_sections/checklists";
import Parametres from "../_sections/parametres";
import Integrations from "../_sections/integrations";
import MonOffre from "../_sections/offre";
import Demarrer from "../_sections/demarrer";

export default function Configuration() {
  return (
    <>
      <div className="page-head"><div><h1>Configuration</h1><p>Tout ce qui se règle une fois : camions, conducteurs, dépôts, checklists, alertes.</p></div></div>
      <Panneau groupe="config" id="demarrer" titre="Mise en route"><Demarrer /></Panneau>
      <Panneau groupe="config" id="flotte" titre="Camions"><Flotte /></Panneau>
      <Panneau groupe="config" id="conducteurs" titre="Conducteurs"><Conducteurs /></Panneau>
      <Panneau groupe="config" id="depots" titre="Dépôts"><Depots /></Panneau>
      <Panneau groupe="config" id="checklists" titre="Checklists de contrôle"><Checklists /></Panneau>
      <Panneau groupe="config" id="parametres" titre="Alertes et société"><Parametres /></Panneau>
      <Panneau groupe="config" id="integrations" titre="Intégrations"><Integrations /></Panneau>
      <Panneau groupe="config" id="offre" titre="Mon offre"><MonOffre /></Panneau>
    </>
  );
}
