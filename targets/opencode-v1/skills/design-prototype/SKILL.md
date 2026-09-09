---
name: design-prototype
description: "Explore or refine visual concepts, user flows and existing Figma designs through Aksel browser sketches or editable Figma components. Use for layout, hierarchy and visual alternatives; use `prototype` for executable behavior and `figma-workflow` to translate a chosen design into code or an implementation brief."
---
# Prototype — fra konsept til synlig skisse

> **OpenCode v1:** Skill names below are exact IDs from the active catalog, not slash commands. Load them with the native `skill` tool. Slash commands are direct user entry points only.

Utforsk designkonsepter interaktivt i nettleseren, iterer med designeren, og
lever Figma-klart — eller som Figma-skisse med ekte Aksel-komponenter når
runtime tilbyr godkjent write.

Bruk `prototype` når usikkerheten gjelder kjørbar oppførsel, datamodell,
tilstandsmaskin eller feilkontrakt. Denne skillen utforsker det designeren kan
se og prøve; en skisse beviser ikke backendlogikk. Bruk `figma-workflow` når
et eksisterende Figma-design allerede er valgt og skal oversettes til en
implementeringsbrief eller kode innenfor den aktive agentens mandat.

## Gate for writes og eksterne sideeffekter

Analyse, lesing av eksisterende Figma-kontekst og lokal visualisering er
read-only for konsumentrepoet. Visual Companion skriver bare til en privat,
midlertidig sesjonsmappe utenfor repoet. Figma-, Issue- og andre eksterne writes
krever eksplisitt mandat for mål, handling og omfang. Brukerens konkrete
bestilling kan gi mandatet; gjenbruk det for operasjonene som fullfører den
bestilte endringen. Når mandat eller et vesentlig valg mangler, vis en kort
preview av mål og endring og spør bare om det som mangler. Nye mål eller utvidet
omfang trenger eget mandat; et fasebytte krever ingen ny godkjenning.

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

Visual Companion er best for **tidlig utforsking** — når retningen er uklar og du
vil se noen tydelige konsepter raskt. Gå videre til Figma når det er bestilt;
nettleserutforsking trenger ingen automatisk Figma-leveranse.

## Fase 1: Visuell utforsking (Visual Companion)

Interaktivt nettleserverktøy for å utforske designkonsepter med Aksel-styling.
Start med ett navngitt designspørsmål som prototypen skal besvare. Hvis dere
ikke kan si hva dere skal lære eller velge, fortsett avklaringen i chatten før
dere lager varianter.

Når nettlesersporet er valgt, les
[Visual Companion-referansen](references/visual-companion.md) før oppstart. Ikke
last den lange referansen i en ren chat- eller Figma-flyt.

### Forutsetninger

- Node.js ≥ 18 (for HTTP-server)
- `@navikt/ds-css` i prosjektets `node_modules` gir ekte Aksel-stiler. Uten den
  fortsetter serveren trygt med fallback-stiler.
- En lokal klient som kan åpne serverens loopback-URL. I cloud/remote-kjøring
  uten klienteksponert loopback: ikke start serveren; bruk chat + Figma.

1. Ikke installer avhengigheter automatisk. Hvis Aksel CSS mangler og korrekt
   stil er nødvendig, vis eksakt kommando og forventede filendringer for repoets
   faktiske pakkebehandler. Be brukeren eller en separat autorisert
   utviklerflyt kjøre den etter eksplisitt godkjenning; Designer skal aldri
   installere pakken selv. Fortsett ellers med fallback-stilene.
2. Når designeren har bestilt eller takket ja til nettleservisning, start serveren:
   ```bash
   # Run from this skill's bundled directory:
   node scripts/server.js --project-dir <consumer-repo>
   ```
   Standard inaktivitetstid er fire timer. Bruk bare
   `--idle-timeout-minutes <1-480>` når økten faktisk trenger en annen grense.
3. Les startup-JSON fra stdout — den inneholder `url`, `screen_dir`, `state_dir`,
   `session_id` og `pid`. URL-en inneholder en tilfeldig sesjonstoken; del den
   bare med designeren som deltar i den lokale økten.
4. Gi designeren URL raskt; for eksisterende flater først etter verifisert før/etter

### Eksisterende flate: nåtilstand først

Klassifiser selv. Bruk issue-/oppgavetekst når det finnes; ellers bruk prompt, side-/rutenavn, komponentnavn og appkontekst. Endring/forbedring/ny komponent på kjent side = eksisterende flate. Ved tvil, anta eksisterende flate.

For eksisterende løsning er dette en gate før første visuelle forslag, også ved Figma/chat:
1. Bruk den Figma-skissen designeren har valgt som utgangspunkt; ellers hent
   faktisk side med Playwright/lokal app først, alternativt en tillatt visuell
   kilde eller et manuelt skjermbilde. En Figma-import krever eget skrivemandat.
2. Verifiser riktig side eller Figma-node. Ved lokal app, fjern ufarlig cookie-
   og modalstøy før screenshot; ikke omgå innlogging. Rediger bort navn,
   fødselsnummer, fritekst og andre personopplysninger fra delte bilder. Bruk
   aldri ekte data, secrets eller autentiserte produksjonsdata i Visual Companion.
3. Vis før/etter med samme viewport, data og sidekontekst; forklar hva som er endret og uendret.
4. Verifiser i den valgte flaten: ved nettleserskisse, åpne Visual Companion og
   sjekk at skjermbilder laster (`naturalWidth > 0`); ved direkte Figma-arbeid,
   inspiser Figma-resultatet. Ikke start en nettleserøkt for en ren Figma-flyt.
5. Aldri rekonstruer eksisterende side fra kode og presenter den som nåtilstand.

### Tilby visual companion

Tilby nettleservisning just-in-time: først når et konkret designspørsmål faktisk
blir lettere å besvare visuelt, ikke som et generelt oppstartsspørsmål. Spør én
gang. Hvis designeren allerede ba om en nettleserprototype, start uten å spørre
på nytt; hvis svaret er nei, jobb videre med tekst og Figma uten nye tilbud.

### Bestemme per spørsmål: nettleser eller chat?

Bruk nettleser når innholdet er visuelt: wireframes, mockups,
layout-sammenlikninger, side-by-side-varianter og komponenteksempler.
Bruk chat for kravspørsmål, scope, konseptuelle valg og avveininger.

### Skrive innhold

Skriv HTML-fragmenter til `screen_dir` (en privat tempmappe utenfor repoet).
Serveren wrapper automatisk i Aksel-temat og laster ekte `@navikt/ds-css` fra
prosjektets node_modules når en trygg, regulær CSS-fil finnes.

**VIKTIG — Aksel-korrekthet:**

Før du skriver en HTML-mockup, sjekk alltid `aksel-design` skill for:
- Riktige komponentnavn og struktur
- Korrekt spacing (token = pixelverdi, f.eks. `--ax-space-16` = 16px)
- Korrekt fargebruk (`--ax-bg-*`, `--ax-text-*`, `--ax-border-*`)

Bruk den bundlede `.aksel-*`-markupen i
`references/aksel-markup-fasit.md` som en **versjonert startreferanse**. Den er
ekte ds-react-output, men ikke en evig Aksel-fasit: verifiser først at consumerens
installerte Aksel-versjon har kompatibel DOM/CSS. Ved avvik er installerbar
pakke, aktuell Aksel-dokumentasjon eller rendret komponent autoritativ. Frame-
malen setter rot-konteksten (`data-color="accent"`). `.mock-*` er bare for
ikke-Aksel-stillas.

Tokens i v8: `--ax-space-{px}` (f.eks. `--ax-space-16` = 16px, `--ax-space-24` = 24px).
Radius: `--ax-radius-4`, `--ax-radius-8`, `--ax-radius-12`.

Se `references/visual-companion.md` for alle CSS-klasser og eksempler.

**Regler:**
- Bekreft at token-URL-ens `/health` svarer før du omtaler økten som aktiv eller
  skriver neste skjerm. Hvis ikke, start en ny økt og del den nye komplette URL-en.
- Semantiske filnavn: `konsept-a.html`, `layout-v2.html`
- Aldri gjenbruk filnavn
- Ved et åpent retningsvalg, lag vanligvis tre strukturelt forskjellige
  alternativer; bruk antallet oppgaven trenger. Ulik copy eller farge alene er
  ikke en ny retning. Avtalte detaljjusteringer trenger ingen nye varianter.
- Bruk samme representative, syntetiske datasett, viewport og omtrent samme
  innholdstetthet i variantene, slik at sammenlikningen blir rettferdig.
- Forklar spørsmålet på siden: «Hvilken tilnærming passer best?»
- Skaler fidelitet etter spørsmålet — wireframe for layout, detaljer for detaljer
- **Norske tegn (æ/ø/å) direkte som UTF-8** — aldri `\u00f8`-escapes; serveren skriver
  ordrett, så escapen blir synlig tekst i skissen («m\u00f8te» i stedet for «møte»)

### Les brukervalg

Etter at designeren har sett skjermen:
1. Les `$STATE_DIR/events.jsonl` for klikk-data. Hendelser inneholder bare
   `type`, en automatisk tildelt ID (`choice-1`, `choice-2`, …), en ugjennomsiktig
   `screen`-ID og timestamp; koble ID-en til rekkefølgen på alternativene i
   HTML-fragmentet med samme `screen`-ID. En ny skjerm nullstiller eventloggen,
   og serveren avviser forsinkede hendelser fra eldre skjermer.
2. Bruk designerens tekstrespons som fasit og klikkdata som støtteevidens.
3. Iterer eller gå videre

### Variant-utforskning

Bruk dette når et retningsvalg står åpent; gjenbruk ellers det avtalte valget.

1. Lag tydelig forskjellige varianter som valgalternativer på skjermen
2. Spør: «Hvilken variant foretrekker du?» med beskrivende navn
3. Iterer på valgt variant
4. Fang valgt variant, hvorfor den vant og eventuelle lånte deler. Behold også
   en observerbar referanse: skjermbilde når mulig, ellers HTML-filnavn,
   screen-/choice-ID og designerens eksplisitte valg. Fortsett til avtalt leveranse.

### Situasjoner brukeren møter

Vis ulike situasjoner som separate mockups eller sekvens: normal, venter (lasting), feil, tom tilstand, og ferdig/bekreftelse.

## Fase 2: Figma-leveranse

Når konseptet er valgt, sjekk Figma read og write som separate kapabiliteter.
Figma MCP-tilstedeværelse alene er ikke en write-garanti. Hvis en eksplisitt
create/edit-kapabilitet finnes, les
[Figma-prototypereferansen](references/figma-prototype.md). Ikke last den lange
referansen under ren chat- eller nettleserutforsking. Bruk
[komponentkatalogen](references/aksel-figma-katalog.json) som en bundlet
oppdagelsessnapshot og [tokenreferansen](references/aksel-figma-tokens.md) for
layouten rundt dem. Det aktive Figma-biblioteket er autoritativt.

1. Finn riktig plan og filkontekst read-only.
2. Bekreft mandat for mål og endring før filoppretting eller redigering.
   Gjenbruk eksisterende mandat; vis preview og spør når noe vesentlig mangler.
3. Søk Aksel først. Bruk en eksisterende komponent når den finnes; bygg custom
   bare når biblioteket faktisk mangler mønsteret.
4. Preflight komponentnøkkel, varianter og tekst-/fontkrav mot det aktive
   biblioteket før første write i økten. Bruk snapshotet til å gjøre preflighten
   målrettet, ikke til å hoppe over den.
5. Bygg inkrementelt, én seksjon per kall, med eksakte navn fra katalog eller
   preflight.
6. Sammenlign Figma-screenshot mot avtalt resultat: valgt Visual Companion-
   retning når den finnes, ellers brukerens valgte Figma-kilde og bestilling
   eller det avtalte konseptet. Bevar ønsket flyt, hierarki og innhold; la aktivt
   Aksel-bibliotek styre komponentstruktur, varianter og tokens. Fiks utilsiktede
   avvik og del oppdatert lenke.

Lever redigerbare komponenter og samle tilstander i én variant-komponent. Når
en komponent skal vises i appens eksisterende sidekontekst, bruk ekte skjermbilde
som bakgrunn og en redigerbar overlay; aldri presenter en håndkodet
rekonstruksjon som nåtilstand. Direkte Figma-iterasjon bruker den avtalte
Figma-strukturen og trenger ikke en ny skjermbildebakgrunn.

## Iterasjon

Vis resultat → designer gir feedback → juster → gjenta til fornøyd.

## UU, opprydding og degradation

- Sjekk kontrast og semantikk i designet. Full WCAG: `accessibility-review` ved overlevering.
- Stopp den eksakte non-blocking/async-sesjonen som startet serveren etter
  leveranse. Ikke signaliser en PID fra gammel metadata; prosess-ID-er kan
  gjenbrukes. Normal stopp og inaktivitet fjerner bare den aktive, markerte
  temp-sesjonen automatisk.
- Etter krasj/strømbrudd: bruk startup-JSON-ens ID og kjør
  `node scripts/server.js --project-dir <consumer-repo> --cleanup <session_id>`.
  Serveren verifiserer markøren og fjerner bare denne sesjonen. Den støtter ikke
  `--cleanup-all`. For flere kjente restsesjoner: vis eksakte ID-er/stier, få
  eksplisitt godkjenning, og rydd én ID om gangen.
- Med bare Figma read → bruk konteksten, men lever Visual Companion,
  Figma-klart utkast eller Issue-utkast; ikke hev at en fil ble skrevet.
- Uten Figma MCP → beskriv konseptet, lever som Issue-utkast.
- Uten Node.js → Chat + Figma direkte (hopp over Visual Companion).
- I cloud/remote uten tilgjengelig loopback-URL → Chat + Figma direkte.
- Uten Playwright → manuelt skjermbilde fra designer.

## Boundaries

### ✅ Alltid
- Bruk Aksel-komponenter og -tokens
- Returner bare URL/Figma-lenke som faktisk finnes
- Bruk handlingsspråk — aldri verktøynavn
- Spør ved uløste designvalg eller endringer utenfor avtalt omfang
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
