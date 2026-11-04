---
status: proposed
date: 2026-11-04
---

# Kjørende apper i appens nettleserfane

Foreslår å erstatte appdelene av ADR 0027, 0029 og 0030 og hele ADR 0032.

Vi bygde «Appen nå» som proxy, inspektør og kontrollskall inne i et canvas. Det
krever en egen tillitsmodell fordi en ubetrodd app vises i en betrodd flate, og
agenten kan ikke se det designeren ser. Copilot-appen har en innebygd nettleserfane
med agentverktøy og Pick & Polish, som legger valgte elementer og områder i neste
melding. Vi flytter derfor kjørende apper dit. Designverksted beholdes for
HTML-skisser, fordi appen ikke har runder, versjoner, vernede felt eller
prosjektlagrede rom. Regelen i ADR 0027 om at app og forslag aldri skal splittes
mellom nettleser og canvas gjelder ikke lenger.

Et forslag til en eksisterende app er en endring i den eide kopien demoen kjører
fra, med privat Git-historikk som angre og overleveringsgrunnlag. Den trenger ingen
egen godkjenning fordi originalprosjektet ikke endres.

## Konsekvenser

- Proxy, appskall, inspektør, appkoblede forslag og `read_preview` fjernes.
  `app-runtime.js` beholdes, fordi appen ikke eier oppstart av demoer.
- Agenten får skjermbilder og sidelesing av samme fane som designeren ser.
- Grensen i ADR 0027 om å holde feltverdier og hemmelige URL-parametre utenfor kan
  ikke holdes. Pick & Polish sender sidens tekst, HTML og full adresse til modellen,
  og fjerner bare attributtene `value`, `password`, `token`, `secret` og `key`.
  Regelen om syntetiske data må bære dette alene.
- Mandatgrensen blir en instruks og en eid kopi, ikke en teknisk sperre.
- Innspill til apper lagres ikke lenger i rom eller besvares per kommentar. Et
  forslag som skal beholdes, lagres som patch og kort brief etter avtale.
- Lagrede approm kan leses, men ikke åpnes.
- Pick & Polish er udokumentert, og appen er i technical preview. Flyten er lest ut
  av koden i app 1.1.34. Klienter uten nettleserfane bruker tilgjengelig nettleser
  med innspill i samtalen.

Beslutningen er foreslått til en prøve i appen med sandkassen på og helst en
designer som ikke kjenner flyten har bekreftet den.
