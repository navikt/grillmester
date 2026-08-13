## Kort fortalt

<!-- Hva forbedrer denne PR-en, for hvem, og hvorfor? -->

## Omfang og pakke

- [ ] Standardpakken `grillmester`
- [ ] NAV-tillegget `grillmester-nav`
- [ ] Distribusjon/release
- [ ] Dokumentasjon/governance

## Kontrakt og provenance

- [ ] Agent-/skill-ID-er og kryssreferanser er gjennomgått.
- [ ] Endringer i tools, modeller, writes eller approval-grenser er eksplisitt beskrevet.
- [ ] `policy/content-lock.json`, provenance og tredjepartsnotiser er oppdatert når nødvendig.
- [ ] Consumer-/teamspesifikke fakta er fjernet eller dokumentert som bevisst lokal evidens.
- [ ] Standardpakken fungerer alene; standard + NAV-tillegget fungerer sammen;
      NAV-tillegget består sin strukturelle install-/uninstall-smoke.

## Verifikasjon

<!-- List eksakte kommandoer og resultater. Ikke lim inn secrets eller sensitiv diagnostikk. -->

- [ ] Pakke- og marketplace-validator
- [ ] Eval-kontrakt og enhetstester
- [ ] Relevant agent-/skill- eller Visual Companion-test
- [ ] Installasjons-/oppgraderingssmoke når payload/distribusjon er endret
- [ ] `git diff --check`

## Manuell RC-evidens

<!-- Ved runtimeendringer: klient, release/source-SHA, sandboxpolicy, resolved modell/tools, godkjent/avvist write og observerte sideeffekter. Skriv «ikke relevant» med grunn. -->

## Release og rollback

<!-- Krever dette versjonsbump? Hvordan oppgraderer og ruller en consumer tilbake? -->
