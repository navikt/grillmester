---
name: grillmester-design-prototype
description: "Utforsk designkonsepter visuelt med Aksel-tema i nettleser, og lever som Figma-skisse. Brukes via /grillmester-design-prototype når et konsept skal visualiseres."
license: MIT
---

# Prototype — fra konsept til synlig skisse

Utforsk designkonsepter interaktivt i nettleseren, iterer med designeren,
og lever som Figma-skisse med ekte Aksel-komponenter.

## Gate for writes og eksterne sideeffekter

Analyse, lesing av eksisterende Figma-kontekst og lokal visualisering er
read-only for konsumentrepoet. Visual Companion skriver bare til en privat,
midlertidig sesjonsmappe utenfor repoet. Før skillen oppretter eller endrer en
Figma-fil, oppretter en Issue eller gjør en annen ekstern write, skal den vise
en kort preview og få et eksplisitt ja til den avgrensede handlingen.
Godkjenning av én handling dekker ikke senere writes.

Ikke opprett branch eller commit, og ikke push, opprett pull request eller
deploy automatisk.

## Når brukes denne?

- Designer vil se et konsept visuelt (ikke bare beskrevet)
- Variant-sammenlikning for å velge retning
- Rask validering av layout, hierarki eller flyt
- Situasjonsdesign — vis alle situasjoner brukeren kan møte

### Når gå rett til Figma (hopp over Fase 1)

- Du itererer videre på et eksisterende Figma-design
- Oppgaven er detaljjustering eller finpuss (spacing, farger, typografi)
- Designeren allerede vet hva de vil og trenger Figma-komponenter
- Komponentbygging og produksjonsnære leveranser

Visual Companion er best for **tidlig utforsking** — når retningen er uklar og du vil se 2-3 konsepter raskt. Når retningen er valgt, gå rett til Figma.

## Fase 1: Visuell utforsking (Visual Companion)

Interaktivt nettleserverktøy for å utforske designkonsepter med Aksel-styling.

### Forutsetninger

- Node.js ≥ 18 (for HTTP-server)
- `@navikt/ds-css` i prosjektets `node_modules` gir ekte Aksel-stiler. Uten den
  fortsetter serveren trygt med fallback-stiler.
- En lokal klient som kan åpne serverens loopback-URL. I cloud/remote-kjøring
  uten klienteksponert loopback: ikke start serveren; bruk chat + Figma.

1. Ikke installer avhengigheter automatisk. Hvis Aksel CSS mangler og korrekt
   stil er nødvendig, vis eksakt kommando og forventede filendringer for repoets
   faktiske pakkebehandler, og kjør bare etter eksplisitt godkjenning.
2. Etter at designeren har takket ja til nettleservisning, start serveren:
   ```bash
   # Run from this skill's bundled directory:
   node scripts/server.js --project-dir <consumer-repo>
   ```
3. Les startup-JSON fra stdout — den inneholder `url`, `screen_dir`, `state_dir`,
   `session_id` og `pid`. URL-en inneholder en tilfeldig sesjonstoken; del den
   bare med designeren som deltar i den lokale økten.
4. Gi designeren URL raskt; for eksisterende flater først etter verifisert før/etter

### Eksisterende flate: nåtilstand først

Klassifiser selv. Bruk issue-/oppgavetekst når det finnes; ellers bruk prompt, side-/rutenavn, komponentnavn og appkontekst. Endring/forbedring/ny komponent på kjent side = eksisterende flate. Ved tvil, anta eksisterende flate.

For eksisterende løsning er dette en gate før første visuelle forslag, også ved Figma/chat:
1. Hent faktisk side med Playwright/lokal app først; alternativt Figma, demo-URL eller manuelt skjermbilde.
2. Verifiser riktig side og fjern/stubb lokal cookie-, login- og modalstøy før screenshot.
   Rediger bort navn, fødselsnummer, fritekst og andre personopplysninger. Bruk
   aldri ekte data, secrets eller autentiserte produksjonsdata i Visual Companion.
3. Vis før/etter med samme viewport, data og sidekontekst; forklar hva som er endret og uendret.
4. Åpne Visual Companion selv før deling og sjekk at skjermbilder laster (`naturalWidth > 0`).
5. Aldri rekonstruer eksisterende side fra kode og presenter den som nåtilstand.

### Tilby visual companion

Spør designeren én gang om nettleservisning når innholdet er visuelt.
Hvis nei — jobb kun med tekst og Figma.

### Bestemme per spørsmål: nettleser eller chat?

Bruk nettleser når innholdet er visuelt: wireframes, mockups,
layout-sammenlikninger, side-by-side-varianter og komponenteksempler.
Bruk chat for kravspørsmål, scope, konseptuelle valg og avveininger.

### Skrive innhold

Skriv HTML-fragmenter til `screen_dir` (en privat tempmappe utenfor repoet).
Serveren wrapper automatisk i Aksel-temat og laster ekte `@navikt/ds-css` fra
prosjektets node_modules når en trygg, regulær CSS-fil finnes.

**VIKTIG — Aksel-korrekthet:**

Før du skriver en HTML-mockup, sjekk alltid `/grillmester-aksel-design` skill for:
- Riktige komponentnavn og struktur
- Korrekt spacing (token = pixelverdi, f.eks. `--ax-space-16` = 16px)
- Korrekt fargebruk (`--ax-bg-*`, `--ax-text-*`, `--ax-border-*`)

Bruk **ekte `.aksel-*`-markup fra `references/aksel-markup-fasit.md`** — generert fra
`@navikt/ds-react` (ds-reacts egen DOM), rendrer autentisk Aksel via ds-css. Frame-malen
setter rot-konteksten (`data-color="accent"`) som gjør primærknapper blå. `.mock-*` er kun
for ikke-Aksel-stillas. Fargene ligger i CSS-en (`data-color`/`data-variant`), ikke i JS.

Tokens i v8: `--ax-space-{px}` (f.eks. `--ax-space-16` = 16px, `--ax-space-24` = 24px).
Radius: `--ax-radius-4`, `--ax-radius-8`, `--ax-radius-12`.

Se `references/visual-companion.md` for alle CSS-klasser og eksempler.

**Regler:**
- Semantiske filnavn: `konsept-a.html`, `layout-v2.html`
- Aldri gjenbruk filnavn
- 2–4 alternativer per skjerm
- Forklar spørsmålet på siden: «Hvilken tilnærming passer best?»
- Skaler fidelitet etter spørsmålet — wireframe for layout, detaljer for detaljer
- **Norske tegn (æ/ø/å) direkte som UTF-8** — aldri `\u00f8`-escapes; serveren skriver
  ordrett, så escapen blir synlig tekst i skissen («m\u00f8te» i stedet for «møte»)

### Les brukervalg

Etter at designeren har sett skjermen:
1. Les `$STATE_DIR/events.jsonl` for klikk-data. Hendelser inneholder bare
   `type`, en automatisk tildelt ID (`choice-1`, `choice-2`, …) og timestamp;
   koble ID-en til rekkefølgen på alternativene i siste HTML-fragment.
2. Kombiner med designerens tekstrespons
3. Iterer eller gå videre

### Variant-utforskning

1. Lag 2–3 varianter som valgalternativer på skjermen
2. Spør: «Hvilken variant foretrekker du?» med beskrivende navn
3. Iterer på valgt variant
4. Når konseptet er valgt — gå til Fase 2

### Situasjoner brukeren møter

Vis ulike situasjoner som separate mockups eller sekvens: normal, venter (lasting), feil, tom tilstand, og ferdig/bekreftelse.

## Fase 2: Figma-leveranse

Når konseptet er valgt, bygg en Figma-skisse av den valgte varianten.

### Krav

Figma MCP-verktøy tilgjengelig.

### Flyt

1. `whoami` → finn planKey
2. Vis preview og få eksplisitt godkjenning → opprett fil, del URL når relevant kontekstgate er passert
3. `search_design_system` → finn relevante Aksel-komponenter
4. `use_figma` **preflight** → importer + logg varianter, default-variant, tekst-node-navn og fonter (se referanse)
5. `use_figma` → bygg skissen **inkrementelt, én seksjon per kall** med eksakte variant-navn og node-navn fra preflight
6. **`get_screenshot`** → parity-gate: sammenlign mot Visual Companion-fasiten (se referanse for sjekkliste)
7. Fiks eventuelle problemer, del oppdatert lenke ved milepæler

**Sjekk katalogen først — den er fasiten.** Alle 45 aktive Aksel-komponenter har key, akser, defaults, tekst-noder og feller ferdig uttrukket i `references/aksel-figma-katalog.json` (maskinlesbar kilde) og `.md` (lesbar). For layouten rundt komponentene (luft, farger, kanter, typografi) bruk `references/aksel-figma-tokens.md`. Drift-validert — hopp over preflight for det katalogen dekker. Detaljer i `references/figma-prototype.md`.

Komponenten (ikke hele siden) er enheten du bygger — men for **eksisterende flater** gir du kontekst via **bakgrunn + redigerbar overlay**: skjermbilde av den ekte siden med et injisert tomt felt, og den redigerbare komponent-instansen plassert oppi (se `references/figma-prototype.md`). Aldri håndkod en tilnærming av modulen inn i skjermbildet — det gir drift; den ekte komponenten er eneste fasit. Lever tilstander som **én variant-komponent** (`Tilstand`-akse), ikke løse statiske rammer, og slå sammen nesten-like tilstander.

### Komponent-gate

Før du bygger i Figma, søk Aksel-biblioteket:

```
search_design_system(query: "<komponentnavn>", fileKey: "<key>")
```

Finnes komponenten? → Bruk den.
Finnes den ikke? → Bygg custom, men med Aksel-tokens.

### Komponent-instansiering

- **Preflight først**: importer + logg varianter, default og tekst-noder i ETT kall
- **Bygg inkrementelt**: ett `use_figma`-kall per seksjon (atomisk — én feil ruller tilbake hele kallet)
- **`defaultVariant` er ofte feil**: GlobalAlert/LocalAlert=Error, Tag=Neutral, Checkbox=unchecked. Antall barn (RadioGroup/Accordion/Tabs) er også en variant-akse — velg bevisst
- **Tekst** via `findOne`/`findAllWithCriteria` med eksakt name (ikke `setProperties()` for tekst); les font med `loadFontAsync(node.fontName)` — Aksel = `Source Sans 3`
- **Komposisjon**: søknadssteg→`FormProgress`; bygg `Table` fra `Table cell`; skjul Slot-placeholdere; `layoutSizingHorizontal="FILL"` kun etter append; farger via `search_design_system` — aldri gjett RGB
- **Leveranse**: samle tilstander i én variant-komponent (`Tilstand`-akse) via `combineAsVariants` — Figma- og Figma Make-vennlig. For sidekontekst: skjermbilde-bakgrunn + redigerbar overlay (aldri håndkodet modul i bildet). Se `references/figma-prototype.md`

Se `references/figma-prototype.md` for fullstendige regler og eksempler.

## Iterasjon

Vis resultat → designer gir feedback → juster → gjenta til fornøyd.

## UU, opprydding og degradation

- Sjekk kontrast og semantikk i designet. Full WCAG: `/grillmester-accessibility-review` ved overlevering.
- Stopp serveren med `kill <pid>` etter leveranse. Normal stopp og inaktivitet
  fjerner bare den aktive, markerte temp-sesjonen automatisk.
- Etter krasj/strømbrudd: bruk startup-JSON-ens ID og kjør
  `node scripts/server.js --project-dir <consumer-repo> --cleanup <session_id>`.
  Serveren verifiserer markøren og fjerner bare denne sesjonen. Den støtter ikke
  `--cleanup-all`. For flere kjente restsesjoner: vis eksakte ID-er/stier, få
  eksplisitt godkjenning, og rydd én ID om gangen.
- Uten Figma MCP → beskriv konseptet, lever som Issue.
- Uten Node.js → Chat + Figma direkte (hopp over Visual Companion).
- I cloud/remote uten tilgjengelig loopback-URL → Chat + Figma direkte.
- Uten Playwright → manuelt skjermbilde fra designer.

## Boundaries

### ✅ Alltid
- Bruk Aksel-komponenter og -tokens
- Returner URL / Figma-lenke for resultater
- Bruk handlingsspråk — aldri verktøynavn
- Spør designer før større endringer
- Del lenker raskt; for eksisterende flater først etter verifisert nåtilstand/før/etter

### 🚫 Aldri
- Skriv kode i prosjektets kildekode eller deleger kodeimplementering
- Opprett branch, commit, push, pull request eller deploy automatisk
- Gjør Figma-, GitHub- eller andre eksterne writes uten eksplisitt godkjenning
- Installer pakker eller endre `.gitignore`, lockfiler eller andre repo-filer som del av lokal preview
- Bruk ekte data, PII, secrets eller produksjonsinnhold i Visual Companion
- Eksponer verktøynavn til designeren
- Feilsøk build-problemer (fall tilbake til neste metode)
- Hopp over UU-sjekk ved leveranse
