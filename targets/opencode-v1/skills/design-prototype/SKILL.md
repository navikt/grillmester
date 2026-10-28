---
name: design-prototype
description: "Explore running local apps, visual concepts and user flows in Designverksted or Figma; read saved design rooms for implementation or briefs. Use `prototype` for uncertain data/state/failure contracts and `figma-workflow` for a chosen Figma design to code or brief."
---
# Fra designspørsmål til synlig resultat

> **OpenCode v1:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Bruk visuelle underlag til å utforske konsepter, hierarki og brukerflyt. Velg
underlag og fidelitet etter det designeren skal vurdere, og gjenbruk avklart
retning og mandat. En konkret designendring gir normalt et synlig forslag;
spørsmål og observasjoner kan besvares uten en ny skisse. Vis bare den faktiske
appen som dagens løsning, og skill den fra forslag og simulerte tilstander.

## Muligheter og valg av arbeidsflate

Designverksted kan vise en kjørende app med innspill og ett interaktivt
HTML-forslag i samme canvas. Selvstendige HTML-skisser kan utforske nye ideer
uten appoppstart. Lagrede skisser har versjoner og en avgrenset editor. Figma
kan brukes når redigerbare designfiler er ønsket leveranse; det er ingen
obligatorisk fase etter en ferdig skisse.

Velg fra hensikten og klientens faktiske kapabiliteter. En eksisterende app er
nyttig som referanse når dens innhold eller oppførsel betyr noe for valget,
men er ingen forutsetning for idéutforsking. Når oppgaven krever et kjørbart
forsøk med en usikker data-, tilstands- eller feilkontrakt, brukes `prototype`.
Et valgt Figma-design til kode eller brief
hører til `figma-workflow`.

Les den relevante referansen **før første handling i den grenen**. Last bare
detaljene som trengs for arbeidet; videre operasjoner kan kreve nye avsnitt.
Bruk klientens verktøy og skjemaer.

| Behov og tilgjengelig kapabilitet | Referanse og hva den eier |
|---|---|
| Åpne en faktisk lokal app i Designverksted | [Appåpning](references/application-opening.md): repoets demooppskrift, eid prosess, tilkobling og åpningskontroll. |
| Gi innspill eller lage forslag med appen som referanse | [App og forslag](references/design-workspace.md#running-application): samme arbeidsflate, publisering og dokumentbinding. |
| Åpne eller videreutvikle en HTML-skisse i canvas | [Designrom](references/design-workspace.md#open-and-continue): lagring, publisering, innspillsrunder, editor og versjoner. |
| Lage en HTML-skisse uten canvas, med lokal Node.js ≥ 18 og tilgjengelig loopback | [Portabel nettleserflyt](references/visual-companion.md): midlertidig server, private filer, CLI-innspill og opprydding. |
| Vurdere eksisterende Figma-underlag | Les den relevante noden med godkjent Figma-kapabilitet. Bruk relevante designskills; vurdering krever ikke write eller publisering. |
| Utforme eller endre et Figma-design med tilgjengelig create/edit-kapabilitet | [Figma-oppskriften](references/figma-prototype.md): bibliotek, redigerbarhet og visuell sammenligning. Verifiser read og write separat. |
| Overlevere eller implementere fra et lagret designrom | [Lesende overlevering](references/design-handoff.md): valgt underlag, kildepar og kontroll av integritet. Åpning av canvas er unødvendig. |

Før HTML-forfatting, bruk `aksel-design` og de felles innholdsreglene for
[Aksel-markup](references/visual-companion.md#aksel-korrekthet-viktig) og
[deklarerte interaksjoner](references/visual-companion.md#justerbare-skisser).
Canvas bruker disse reglene, ikke den portable oppstarts- og innspillsløkken.
Gjenbruk allerede verifiserte komponenter og stiler; undersøk ny komponent,
versjonsendring eller konkret avvik når det oppstår.

## Arbeidsflate, mandat og lagring

Hold app og tilhørende forslag i samme eide verksted. Den første nativeflyten
er inne i Copilot; den private rendereradressen skal ikke åpnes eksternt.
Canvasfeil håndteres etter referansen uten konkurrerende server, pollingsløkke
eller ny skriver. Uten canvas kan faktisk app undersøkes i tilgjengelig nettleser
med innspill i samtalen. Bevar underlaget og avklar et vesentlig formatbytte.

Et designrom gir ikke mandat til produktkode, Git-handlinger eller publisering.
Separat bestilt kodearbeid skjer utenfor canvas i en uttrykkelig eid arbeidskopi;
kontroller at serveren bruker kopien, og bevar originalprosjekt og urelatert arbeid.
En worktree alene beviser ikke at mappen er disponibel. Eksterne writes krever
mandat for mål, handling og omfang; gjenbruk det som allerede er gitt.

Før en ny selvstendig skisse, avklar én gang om den skal lagres eller være
midlertidig, med mindre det er valgt. Appinnspill og oppfølgende forslag er
midlertidige uten avtalt lagring; fortsett uten et nytt lagringsspørsmål og si
kort at arbeidet er midlertidig. Bestilt lagring av hele verkstedet omfatter
forslaget i avtalt designområde; lagring av bare innspill gjør det ikke.
Følg referansens muligheter for senere lagring og gjenåpning. Et helt midlertidig
approm kan foreløpig ikke oppgraderes til lagret arbeid.

Canvas publiserer gjennom bundne handlinger. Bare den portable flyten skriver
HTML direkte til den private tempstien fra aktiv startup-JSON. Historiske
revisjonsfiler skal bevares byte-eksakt, også ved Git-levering. Les
[lagringsreglene](references/design-workspace.md#open-and-continue) før commit
av et rom; formattering og linjeslutt-konvertering kan bryte integriteten.
Et vernet felt endres eller frigis av designeren i editoren; en beskjed i
samtalen frigir det ikke. Et separat produktkrav krever ikke endring av rommet.

Bruk syntetiske data og delte bilder uten personopplysninger eller hemmeligheter.
Nødvendige installasjoner, klient-/sandboxendringer og byggreparasjoner er
separat oppsett med mandat, ikke automatisk feilretting av preview.

## Design og verifikasjon

Lag den minste sammenhengende skissen som lar designeren vurdere oppgaven.
Varianter er nyttige ved reelle retningsvalg; behold valgt retning ved
justeringer. Bruk sammenlignbare utsnitt, data og innholdstetthet når alternativer
vurderes. Knytt observasjoner til faktisk element og tilstand.

- Bruk Aksel-komponenter, tokens og verifisert markup med kompatible stiler.
  Vis fallback eller wireframe ærlig når komponentfidelitet mangler.
- Skisser har deklarerte interaksjoner, ikke fri JavaScript eller appens backend.
  Synlige kontroller skal gjøre det teksten lover eller merkes ved kontrollen
  som statiske eksempler. Merk simuleringer og illustrative tall der de brukes.
- Kontroller relevant gjengivelse og berørte tilstander før resultatet meldes
  klart. Følg [visuell kontroll](references/design-workspace.md#inspect-the-rendered-sketch)
  for canvas. Åpningsstatus, kildekode og lastet CSS er ikke visuell verifikasjon.
- Skaler kontrollen til endringen: innhold, smal flate, relevant zoom, tastatur,
  fokus og berørte feil-/tomtilstander. Full kontroll av uendret flyt trengs ikke
  ved hver justering. Bruk `accessibility-review` for full review av implementert UI.
- Skill målt feil, designavveining og hypotese til brukertest. Uten nødvendig
  visuell tilgang beholdes resultatet som ukontrollert utkast; fortsett uavhengig
  arbeid og be bare om underlag som et konkret valg avhenger av.

Følg den valgte referansens innspillsløp: arbeid med riktig dokument, innsendt
runde og versjon. Usendte notater er ikke bestillinger. Bevar tidligere føringer
og manuelle valg. Publiser og verifiser endringer før de meldes fikset; svar på
spørsmål uten unødvendig ny versjon. Et besvart innspill betyr ikke endret app.

## Overlevering og avslutning

Ved lagret underlag, les overleveringsreferansen før avhengig arbeid. For skisser,
verifiser valgt HTML-/descriptor-par med hash og byteantall; descriptorens
lagrede verdier kan overstyre HTML. Stopp ved avvik. Denne leseflyten krever
verken canvas, Node, romendring eller ny lagring. En brief bestiller ikke kode.
Et midlertidig forslag kan være underlag fra sin gjeldende publiserte versjon
i den eiende samtalen. Følg [overleveringsreferansen](references/design-handoff.md#connect-app-feedback-to-a-sketch-proposal);
ikke krev et nytt lagret rom bare for å bruke tilgjengelig underlag.

Returner bare URL/Figma-lenke som faktisk finnes. I verkstedet holder
hva som kan prøves under Forslag; eksakt versjon og prosjektsti hører til avtalt
overlevering. Oppgi vesentlige begrensninger kort. Midlertidig arbeid lover ikke
varig gjenåpning, og en skisse er ikke ferdig produktkode.

Før lukking eller gjenåpning, les [appens livsløp](references/design-workspace.md#initial-native-support)
eller [skissens livsløp](references/design-workspace.md#open-and-continue) etter
romtype. Stopp bare eid arbeid; canvaslukking og demostopp er forskjellige handlinger.
