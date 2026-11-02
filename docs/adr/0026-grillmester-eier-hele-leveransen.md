---
status: accepted
date: 2026-11-02
---

# Grillmester eier hele leveransen

Erstatter delvis ADR 0005, 0006, 0008 og 0024 for agentutvalget og delegering
av implementering.

To offentlige innganger for utvikling, Grillmester og Barista, tvang brukeren
til å klassifisere oppgaven før den var undersøkt. Den obligatoriske
R3/R4-overleveringen til Kokk flyttet implementeringskonteksten uten å gi et
tydeligere skille mellom forfatter og kontrollør, fordi Grill-inspektør
allerede gjør reviewen i en egen, skrivebeskyttet kontekst. Vi fjerner derfor
Barista og Kokk. Grillmester undersøker, implementerer, tester og leverer selv
på alle risikonivåer og laster metoder fra skills ved behov.

## Beslutning

- Barista og Kokk fjernes fra kildene, content-lock, generatorene og
  releasekontraktene. Proveniens og historiske bevis beholdes.
- Lagret `agent: barista` leses som `grillmester`. Et eksplisitt
  `--agent barista` avvises med beskjed om å bruke `--agent grillmester`. En
  bunt som er pakket ut over en eldre installasjon med Barista- eller
  Kokk-filer, avvises med beskjed om å bruke en ny, tom mappe.
- En R3/R4-endring kan fortsatt bare kalles klar til merge når Grill-inspektør
  gir `APPROVED`, et menneske har godtatt hver vesentlige bekymring, eller et
  menneske uttrykkelig har frafalt inspeksjonen. Selvreview og tester
  erstatter ikke dette.
- Grill-inspektør får `include-custom-instructions: true`. Uten innstillingen
  gir ikke Copilot `AGENTS.md` eller `copilot-instructions.md` videre til en
  egendefinert agent som kjører som subagent. Feltet virker fra Copilot CLI
  1.0.86; eldre klienter laster agenten med en advarsel. Grillmester oppgir
  derfor også stiene til repoets instruksjonsfiler og risikoklassen i
  review-forespørselen.
- Den fokuserte profilen inneholder Grillmester og Grill-inspektør med de samme
  sju skillsene.
- Hybridprofilen i OpenCode låser Grill-inspektør, ikke en implementør, til en
  lokal modell. OpenCode-smokene bruker inspektøren til `.env`- og
  skillscenariene og Grillmester til godkjent skriving.

## Konsekvenser

Full pakke har tre offentlige og tre interne agenter. All implementering bruker
Grillmesters modell, så det finnes ikke lenger en egen, billigere modell for
implementering. Grillmester delegerer ikke implementering; parallelt arbeid
startes i en egen sesjon eller worktree.
