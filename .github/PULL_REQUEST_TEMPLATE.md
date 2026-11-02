## Kort fortalt

<!-- Hva endres, for hvem og hvorfor, og hvor bør revieweren se først? Ta med den minste skissen som gjør endringen tydelig når tekst ikke holder: et kalltre, et mappetre eller en kort diff. -->

## Kontrakt og provenance

- [ ] Agent- og skill-ID-er og kryssreferanser er gjennomgått, og endringer i tools, modeller, writes eller godkjenningsgrenser er beskrevet.
- [ ] `policy/content-lock.json`, provenance og tredjepartsnotiser er oppdatert når kilder eller lineage er endret.
- [ ] Consumer- eller teamspesifikke fakta er fjernet eller dokumentert som bevisst lokal evidens.

## Bevis

<!-- Før og etter: testen, kommandoutskriften eller skjermbildet som viser endringen, med kommandoer, resultater og exit-koder. Ved runtimeendringer: klient, release- eller kilde-SHA, resolved modell og tools, godkjent og avvist write, og observerte sideeffekter; ellers «ikke relevant» med grunn. Ikke lim inn secrets eller sensitiv diagnostikk. -->

- [ ] `git diff --check`

## Release og rollback

<!-- Enveis- eller toveisdør: kan endringen rulles enkelt tilbake? Hvem eller hva kan bli berørt? Krever den versjonsbump, og hvordan oppgraderer og ruller en consumer tilbake? -->
