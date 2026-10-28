# Designverksted: grunnlag for native levering

Status 28. oktober 2026: Den samlede flyten er prøvd i **Copilot app 1.1.33
på macOS**. Resultatene gjelder kandidatene som faktisk ble prøvd. Senere
rettelser må verifiseres mot endelig kilderevisjon før utrulling.

## Omfang

**Appen nå**, innspillsrunder og ett interaktivt HTML-forslag hører til samme
canvas og samtale. Forslaget har egne innspill og lagrede versjoner. Appens
produktkode endres ikke fra verkstedet. Idéutforsking kan starte med skisser
uten demo; en bestilling om bare visning oppretter ikke et forslag.

Første leveranse bruker én arbeidsflate inne i Copilot. Den private
rendereradressen skal ikke åpnes i en ekstern nettleser. Andre verter og
versjoner trenger egen verifikasjon: canvasstøtte alene garanterer ikke
lagringsisolasjon. Se [tillitsgrensene](../trust-and-client-support.md#designverksted-og-overlevering-mellom-klienter)
og [ADR 0027](../adr/0027-designverksted-for-kjorende-apper.md).

## Verifiserte resultater

Prøvene brukte isolerte appkopier og syntetiske data.

| Område | Resultat og avgrensning |
| --- | --- |
| Native kjerneløp | Appbruk, samlet innsending, umiddelbar sendestatus, retur til Prøv og automatisk oppfølging uten ekstramelding bestod. Et klikkbart forslag kom i samme canvas. Presise skisseinnspill ga synlige revisjoner med bare de bestilte tekstendringene. |
| Native gjenåpning | En ny samtale åpnet lagret approm, forslag, tidligere runder og svar. Historiske runder ble ikke sendt på nytt. Et nytt skisseinnspill etter gjenåpningen startet oppfølging og ga en fungerende revisjon. |
| Demoens levetid | Oppstarten gjennom den eide CLI-hjelperen ble ferdig mens demoen fortsatt var tilgjengelig. Uttrykkelig stopp stengte demoen uten observert omstart. Canvaset ble lukket med panelets UI-kontroll; lukking gjennom samtalen alene er ikke bekreftet. |
| Native apptransport | MSW-avskjæring og oppstrømskall bestod. En HMR-endring ble synlig med feltverdi beholdt; dokumentidentitet ble ikke målt. Ingen produktkode i originalappen ble endret. |
| Lokal regresjon | Adapter, proxy, forslag, lagring, avbrudd, gjenoppretting og smale flater er prøvd med automatiserte nettlesertester og simulert samtalevert. Testene erstatter ikke kontroll av den native vertens panelhåndtering og samtalekø. |
| Klientkompatibilitet | CI med eksakte, checksumkontrollerte releaseklienter består på macOS arm64 og Intel, inkludert full og fokusert kontekst, npm-tilgang og GitHub-grenser. Installasjon, oppdatering og rollback er også prøvd isolert. Se [klientkontrakten](../../scripts/release_test_baseline.py). |

## Kjente begrensninger

- **Flere samtidige canvas:** Etter lukking av et valgt, gjenåpnet verksted ble
  et annet stående på vertens «Loading canvas…». Visningen kom tilbake, men
  årsaken er uavklart. Ett fungerende verksted bekrefter ikke denne sekvensen.
- Oppstartskommunikasjonen er fortsatt tidvis teknisk og omfattende. Korte
  sluttsvar er observert, men konsekvent forståelig språk og riktig tolkning av
  ulike designbestillinger er ikke ferdig validert.
- Ekte skjermlesere og brukertester med uavhengige Nav-designere gjenstår.
  Tekniske tester alene dokumenterer ikke en sømløs arbeidshverdag.
- Midlertidig arbeid, ulagret tekst og appens skjematilstand loves ikke bevart
  etter lukking. Lagret arbeid kan gjenåpnes; et ubrukelig kontrolldokument må
  lukkes før en ny instans kan overta det lagrede rommet.

En vellykket HTTP-respons eller readiness-status beviser ikke korrekt visuell
oppførsel. Iframe-retry er heller ikke en ny isolert lagringskontekst.

## Før utrulling

1. **Sluttprøve i støttet vert.** Kontroller app → innspill → forslag → revisjon,
   lagring, stopp og gjenåpning på endelig kandidat. Åpne to verksteder A og B,
   lukk A, gjenåpne A og lukk den valgte visningen igjen. Krev ny interaksjon og
   serverrespons fra B. Behold avvik åpent til sekvensen er bekreftet. Prøv også
   gamle kapabiliteter og ingen replay.
2. **Eierskap og regresjon.** Bevar originalprosjekter og nettverksgrenser.
   Restart eller tapt eierskap til demoen krever at tilhørende visninger
   avsluttes før ny tilkobling; URL og pinnet DNS beviser ikke prosessidentitet.
   Følg [ADR 0028](../adr/0028-eid-livslop-for-lokale-demoer.md) og kjør kontrollene
   i [AGENTS.md](../../AGENTS.md), inkludert app- og verkstedsmoke, eksakte
   releaseklienter og deterministisk regenerering.
3. **Innhold og rettigheter.** [Rettighetsjournalen](../../policy/stable-rights-approval.json)
   er bundet til innholdsreview #90 med beslutning #56 bevart. Nye endringer i
   det bundne innholdet krever oppdatert review og binding; hashoppdatering alene
   er ikke godkjenning. Nye kilde-, komponent- eller navneomfang krever egen
   rettighetsvurdering. Kilde- og lisensnotiser skal beholdes.
4. **Publisering.** Følg [release-runbooken](../release-runbook.md): velg ny
   versjon, bygg bunten to ganger fra eksakt source-SHA og kontroller identiske
   bytes, manifest og SHA-256. Bruk eksisterende katalog- og releaseflyt.
   Bekreft installasjon og oppdatering etter publisering. Native app-, CLI- og
   øvrig klientatferd må verifiseres hver for seg.
