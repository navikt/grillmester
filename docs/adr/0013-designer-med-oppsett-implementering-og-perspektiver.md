---
status: accepted
date: 2026-09-25
---

# Designer med oppsett, inline implementering og spesialistperspektiver

## Kontekst

Designer var design-only. Rollen kunne bare kjøre Visual Companion-serveren,
fikk ikke endre filer i repoet eller installere noe, og skulle aldri delegere
til en annen agent. Grensen skulle hindre at Designer ble en
implementeringsagent. I praksis stengte den også ute oppsett av designerens egne
verktøy, som MCP-tilkoblinger og cplt, slik at brukeren måtte bytte til
Grillmester for vanlig maskinoppsett.

Designere har i andre sammenhenger hatt stor nytte av å hente inn flere
spesialistblikk på samme design samtidig, for eksempel UX-ekspert,
innholdsdesigner, UU-ekspert og personas for ulik bruk av løsningen. Klientens
generelle subagenter kan skrive og har ingen fast modell, så de gir ikke en
trygg eller forutsigbar ramme for dette.

## Beslutning

- Designer bruker `claude-opus-5.5` og får samme runtime-verktøy og
  godkjenningsflyt som Grillmester for oppsett av maskin og verktøy. Hemmeligheter
  legges aldri i filer, kommandoer eller output.
- Designer kan implementere når brukeren ber om det, men gjør det selv i samme
  samtale. Den delegerer aldri kodeimplementering til Kokk eller en annen agent.
  Verifikasjonen følger Barista: fokuserte tester der repoet har en testsøm,
  repoets påkrevde sjekker og `/review` før leveranse. Ved høy risiko anbefaler
  Designer Grillmester én gang, men venter ikke på svar og fortsetter med
  mindre brukeren bytter agent.
- Git-handlinger, pull requests og eksterne writes krever fortsatt eksplisitt
  bestilling. Designutforsking blir aldri stille til kode.
- En ny intern rolle, `perspektiv`, tar ett fagperspektiv eller én syntetisk
  persona per kall. Designer bestemmer perspektivet i briefen, kan kjøre flere
  parallelt og eier syntesen og anbefalingen. Rollen kan bare lese, har
  `claude-opus-5.5` og er skjult som Kokk: `user-invocable: false` i Copilot og
  `mode: subagent` med `hidden: true` i OpenCode.
- Syntetiske personas er hypoteser, ikke brukerinnsikt. De bygges aldri på ekte
  personopplysninger, og panelet erstatter ikke brukertesting.
- Designer kan delegere bare til `perspektiv` og `researcher`. OpenCode-policyen
  håndhever dette med en eksplisitt `task`-allowlist.

## Konsekvenser

Designer er ikke lenger et design-only-løfte. Validatoren håndhever i stedet at
Designer aldri delegerer kodeimplementering, og at `perspektiv` beholder
persona-grensen. Pakka får åtte agenter, og alle tellinger, launchere og
release-kontrakter følger den nye rosteren.

Designer har ingen egen implementerer, så uavhengig review av Designers kode
krever at brukeren går videre med Grillmester. Implementeringsmuligheten
omtales nøkternt i dokumentasjonen og promoteres ikke som Designers hovedoppgave.

Endret innhold i Designer og de Hovmester-importerte design-skillene endrer
digestene som rettighetsjournalen binder. Endringen ligger innenfor samme kilde,
komponent og navngivning som den underliggende rettighetsbeslutningen. Derfor
bindes journalen på nytt med `bump_version.py --rights-review` og pull requesten
som gjennomgår innholdet. `perspektiv` er skrevet i Grillmester og hører ikke
til rettighetsomfanget.
