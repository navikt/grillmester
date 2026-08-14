---
name: grillmester-klarsprak
description: "Writes or edits clear Norwegian prose without changing its technical meaning. Use for user-facing text, documentation, README text, ADR prose, pull-request descriptions or requests to remove anglicisms and AI-like phrasing."
---

# Klarspråk

Stram inn norsk prosa uten å endre beslutninger, kontrakter eller teknisk
betydning.

## Oppdag språkreglene først

Ikke anta at hele repositoryet bruker samme språk.

1. Finn consumer-eide språkregler for den konkrete artefakttypen og pathen.
2. Identifiser målgruppe, bokmål/nynorsk, tone og regler for domeneord,
   tekniske termer, kodeidentifikatorer og logger.
3. Behandle eksisterende tekst som evidens bare når den er konsekvent; tilfeldig
   historikk er ikke automatisk en standard.
4. Hvis en nødvendig språkregel mangler, spør brukeren. Ikke innfør en generell
   norsk/engelsk-policy gjennom en språkvask.

Bevar literals, API-felter, identifikatorer og etablerte domenetermer nøyaktig
når en endring ville endre kontrakten.

## Arbeidsflyt

1. Avklar om oppgaven er ren språkvask eller også innholdsredigering.
2. Marker fakta, beslutninger, normative krav og kodeord som ikke skal endres.
3. Skriv om med kortere setninger, aktive verb og tydelig handling.
4. Kontroller at tall, modalverb, negasjoner, vilkår og ansvar fortsatt betyr
   det samme.
5. Vis vesentlige meningsnære valg hvis flere formuleringer er mulige.

## Operative regler

- Start med utfallet eller handlingen leseren trenger.
- Hold ett hovedpoeng per setning.
- Bruk aktiv form og konkrete subjekter.
- Kutt gjentakelser, fyllord og kunstige oppsummeringer.
- Bruk tekniske termer etter consumerens policy. Hvis ingen policy finnes, spør
  før du oversetter eller fornorsker etablerte termer.
- Bruk bindestrek i norske sammensetninger med engelske fagtermer når det er
  naturlig.
- Fjern svulstige AI-markører og falsk symmetri uten å gjøre teksten monoton.
- Bruk Nav i løpende tekst når virksomheten omtales; bevar offisielle navn og
  kodeidentifikatorer som de er.
- Ikke ta med personopplysninger, tokens eller secrets i brukerrettede
  feilmeldinger eller eksempler.

## Grenser

### Alltid

- Bevar teknisk betydning og dokumentert artefaktform.
- Skill språklige forslag fra innholdsendringer.
- Følg den mest spesifikke consumer-eide språkregelen.

### Spør først

- Omstrukturere et helt dokument.
- Endre terminologi som inngår i domene- eller API-kontrakter.
- Publisere, kommentere eksternt eller opprette PR/issue; vis mål og få
  eksplisitt godkjenning.

### Aldri

- Gjette målform, språkvariant eller loggspråk.
- Endre en beslutning under dekke av språkvask.
- Erstatte et kodeord eller domeneterm bare fordi et norsk synonym finnes.

## Referanser ved behov

- [Fagtermer og teksttyper](./references/fagtermer-og-anglisismer.md)
- [Før og etter](./references/for-og-etter.md)
- [AI-markører](./references/ai-markorer.md)
