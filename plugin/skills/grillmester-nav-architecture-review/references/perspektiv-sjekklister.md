# Tre perspektiver for Nav-arkitektur-review

Dette er en spørsmålsbank, ikke Nav-policy eller en fasit. Bruk bare spørsmål
som passer den faktiske endringen. For hvert svar: pek på consumer-evidens eller
en oppdatert autoritativ kilde, og merk ukjente forhold som ukjent. Ikke gjør et
plattformmønster normativt bare fordi det er vanlig i andre Nav-repoer.

Prioriter kilder i denne rekkefølgen:

1. consumerens kode, manifester, ADR-er og eksplisitte policy;
2. aktuell dokumentasjon fra plattform-, sikkerhets- eller produkteier;
3. verifiserte mønstre i sammenliknbare tjenester;
4. antakelser som må avklares før beslutning.

## Arkitektur

- Hvilket bruker- eller systemutfall eier løsningen, og er ansvaret avgrenset?
- Hvilke produsenter, konsumenter og berørte team er verifisert?
- Hvilke råd må innhentes fordi beslutningen krysser team- eller
  plattformgrenser?
- Finnes en støttet plattformkapabilitet for behovet? Verifiser at den faktisk
  dekker identitet, dataflyt, drift og feilhåndtering før den velges.
- Er synkron eller asynkron kobling valgt ut fra konsistens, latenstid,
  feiltoleranse og eierskap – ikke en generell «Nav-standard»?
- Er kontrakten eksplisitt, bakoverkompatibel og mulig å migrere uten delt
  database eller koordinert big-bang?
- Hvilke avhengigheter er vanskelige å reversere, og hva er exit-/migreringsstien?
- Hvordan påvirkes deployfrekvens, ledetid, feilrate og gjenoppretting? Ikke
  krev DORA-måling dersom consumeren ikke bruker den.

## Sikkerhet og personvern

Ved ny entry point, sensitiv dataflyt eller endret identitetsmodell: bruk
`grillmester-security-review` for trusselmodellering.

- Hvilken dataklassifisering og hvilket behandlingsgrunnlag er **faktisk**
  dokumentert av consumeren eller autoritativ Nav-policy? Ikke bruk en statisk
  klassifiseringsliste fra denne pluginen.
- Hvem er caller og subject i hver flyt, og hvilken gjeldende identitetsmekanisme
  støtter akkurat denne relasjonen? Verifiser mot kontrakten og
  `grillmester-auth-overview` når den er installert.
- Er autentisering, autorisasjon og delegering tydelig skilt?
- Matcher Nais `accessPolicy` den observerte service-discovery-/token-grant-
  grafen med minst nødvendige regler, uten å anta navn, namespace eller
  cluster? Vurder ingress, edge-auth og eksterne callers separat; inbound-
  policyen er ikke en komplett trafikkgraf eller ingressbrannmur.
- Kan personopplysninger, hemmeligheter eller fritekst havne i logger,
  telemetri, køer, cache, feilresponser eller analyseflater?
- Krever endringen DPIA, sikkerhets-/personvernråd eller beslutning fra en
  navngitt eier? Ved tvil: eskaler; ikke konkluder på vegne av eieren.
- Finnes et søkbart og forholdsmessig auditspor for sensitive operasjoner, og
  er tilgang og lagringstid forankret i aktuell policy?

## Plattform og drift

- Hvilke workload- og ressursmekanismer støttes av dagens Nais-dokumentasjon og
  consumerens manifesttype?
- Er CPU-/minne-requests, minnegrense, replikaer og autoskalering basert på
  telemetri og forventet last? Nais anbefaler normalt å utelate CPU-limit, men
  dokumenterer unntak blant annet for ytelsestesting; begrunn avvik begge veier.
- Matcher startup-, readiness- og liveness-prober de reelle endepunktene og
  livssyklusfasene? Ikke kopier standardstier.
- Hvilke feilmoduser må kunne observeres i logger, metrics og traces, og hvilke
  alarmer/runbooks finnes faktisk?
- Hvordan bygger, tester og deployer **dette repoet**? Beskriv den observerte
  pipeline og godkjenningsgrensene; ikke dikt opp en «standard workflow».
- Hva er verifisert rollback eller forward-fix for kode, manifest, database og
  meldingskontrakter? Ikke anta at `kubectl rollout undo` er tilgjengelig eller
  riktig.
- Hvilke kostnader, kvoter, backup-/restorekrav og beredskapsansvar er bekreftet
  av eierne før produksjonssetting?

## Primærkilder som skal sjekkes på nytt

- [Nais-dokumentasjon](https://docs.nais.io/)
- [Nais: cost optimization](https://docs.nais.io/workloads/how-to/cost-optimization)
- [Nais: good practices](https://docs.nais.io/workloads/explanations/good-practices/)

Lenk i reviewen til de konkrete sidene og datoen de ble kontrollert. Consumer-
eller Nav-intern policy kan være strengere enn offentlige plattformråd.
