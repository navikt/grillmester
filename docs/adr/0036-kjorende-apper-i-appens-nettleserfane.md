---
status: accepted
date: 2026-11-04
---

# Designflyt i appens nettleserfane

Erstatter Designverksted og Visual Companion, altså ADR 0017, 0019,
0021–0023, 0025, 0027 og 0029–0032. ADR 0028 om eid demolivsløp gjelder videre.

Vi bygde et eget canvas for skisser og kjørende apper, med proxy, innspillsrunder,
versjoner og lagrede rom. Copilot-appen har en innebygd nettleserfane med agentverktøy
og Pick & Polish, som legger valgte elementer og områder i neste melding. I den første
prøven endret Designer ekte React-kode i en midlertidig kopi og viste resultatet i
samme fane. Vi skisser i all hovedsak på eksisterende apper, og der gir ekte
komponenter bedre fidelitet enn håndskrevet HTML. Vi flytter derfor hele designflyten
til nettleserfanen og fjerner Designverksted.

Et forslag er en endring i en eid kopi med privat Git-historikk. Den trenger ingen egen
godkjenning fordi originalprosjektet ikke endres. Det gjelder også oppstart og
installasjon fra låst lockfile i kopien. Lokal demo er førstevalget fordi endringer da
vises i samme fane, og en publisert demo med syntetiske data er reserve. En ny idé uten
app bygges som en liten Aksel-app. Fri prototyping utenfor Aksel er vanlige filer i
samme fane, ikke en egen motor eller skill.

## Dette videreføres

- Skillet mellom dagens app og forslag, og merking av simulert innhold.
- Versjoner, nå som commits i kopiens private historikk.
- Varianter ved reelle retningsvalg, nå bak en query-parameter med én fane per variant.
- At deler designeren vil beholde og tekst designeren har gitt, står til et nyere ønske
  endrer dem.
- Midlertidig som standard, og uttrykkelig lagring som patch og brief.

## Konsekvenser

- Canvas, HTML-motor, editor, innspillsrunder og portabel server fjernes. Bare
  `app-runtime.js` beholdes, fordi appen ikke eier oppstart av demoer.
- Figma får et bedre underlag: siden viser hvilke Aksel-komponenter og varianter den
  bruker, og de slås opp i katalogen vår.
- Svar per kommentar, direkte tekstredigering og vernede felt forsvinner. Innspill lever
  i samtalen.
- CLI og OpenCode har ingen strukturert innspillsflate. De viser demoen i en vanlig
  nettleser med innspill i samtalen.
- Grensen i ADR 0027 om å holde feltverdier og hemmelige URL-parametre utenfor kan ikke
  holdes. Pick & Polish sender sidens tekst, HTML og full adresse til modellen, og fjerner
  bare attributtene `value`, `password`, `token`, `secret` og `key`. Regelen om syntetiske
  data må bære dette alene.
- Mandatgrensen blir en instruks og en eid kopi, ikke en teknisk sperre, og appøkter kjører
  i ekte checkout. Målt med en liten modell i CLI hoppet Designer over skillen i 4 av 4 kjøringer av
  «vis meg appen», og rene endringsønsker kunne gå rett i prosjektet. Designer forhåndslaster
  derfor skillen med `skills`-feltet og har regelen øverst og nederst i prompten. Da var
  prosjektet urørt i 22 av 23 kjøringer. Sterkere modeller og selve appen er ikke målt.
- Stegene hver kjøring trenger, ligger i `SKILL.md` med fullføringskriterier, og referansen
  holder det bare noen kjøringer trenger.
- Lagrede rom kan fortsatt leses som filer, men ikke åpnes.
- Pick & Polish er udokumentert, og appen er i technical preview. Flyten er lest ut av
  koden i app 1.1.34 og prøvd i appen på én app. Uten plukkeren virker flyten fortsatt med ord og
  skjermbilder.
