# Visual Companion: klientkapabiliteter og akseptprøver

Kildekontroll: 2026-10-23. Matrisen skiller dokumenterte klientkapabiliteter fra
det som må prøves i en konkret installasjon. Den er ikke en rapport om bestått
livekjøring i Copilot. [Nettleserscenarioene](visual-companion-scenarios.md)
tester verktøyets oppførsel med syntetisk innhold, uten å bevise klientens
prosesslevetid, verktøyvalg eller videreføring av en samtale.

## Klientmatrise

| Flate | Dokumentert grunnlag | Betydning for skisseøkten | Krever måling |
| --- | --- | --- | --- |
| Copilot app, lokal repository/worktree | Plugins, skills og custom agents. Appen bygger på CLI, men tilbyr ulike lokale og skybaserte kjøreplasser. | Velg Designer fra faktisk lastet katalog. Bevis både nettlesertilgang og vellykket `comments.js list` fra aktiv runtime. | Verktøygrense, serverlevetid og behandling av ventekallets resultat i den installerte appversjonen. [Tilpasning](https://docs.github.com/en/copilot/how-tos/github-copilot-app/customize-github-copilot-app), [sesjoner](https://docs.github.com/en/copilot/how-tos/github-copilot-app/agent-sessions). |
| Copilot CLI, lokal og interaktiv | Plugins og custom agents; klienten kan følge bakgrunnskommandoer. Lokale komponenter kan skygge plugin-komponenter. | Bekreft hvilken skill/agent som faktisk lastes. Behold serverens eksakte verktøyhåndtak, og les resultatet fra avgrenset venting. | Avsluttet tur → automatisk ny behandling av vanlig nettleserinnspill er ikke bekreftet. [Pluginreferanse](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference), [kommandoreferanse](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference). |
| Copilot CLI, programmatisk `-p` | Klienten avslutter etter oppgaven. `COPILOT_TASK_WAIT_TIMEOUT_SECONDS` begrenser etterventing på bakgrunnsjobber; dette er ikke en generell shellgrense. | Ikke presenter prompt-mode som en varig designøkt. En levende server alene beviser ikke at innspill behandles. | Avslutning og opprydding må prøves separat. [CLI-modi](https://docs.github.com/en/copilot/concepts/copilot-surfaces/copilot-cli), [kommandoreferanse](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference). |
| VS Code | Pluginstøtte avhenger av harness og format. Integrert nettleser tilbyr verktøy, elementkommentarer og deling av en eksisterende fane. | Bruk tilgjengelige nettleserverktøy til visuell verifikasjon; behold innsendte runder som beslutningsgrunnlag. Ikke overfør disse klientløftene til appen. | Samspill med skissens sandboxede iframe og valgt harness. [Plugins](https://code.visualstudio.com/docs/agent-customization/agent-plugins), [nettleserverktøy](https://code.visualstudio.com/docs/agents/run/browser-tools). |
| Cloud sandbox / fjernvert | Kommandoer kan kjøre på en annen maskin. Cloud agents Playwright kan nå localhost i sitt eget miljø. | Intern tilgang beviser ikke at designeren kan åpne skissen. Bruk eksisterende chat/Figma-fallback uten verifisert klienteksponert URL som bevarer sikkerhetskontrakten. | Brukertilgang, portvideresending og eksakt origin. [Sandkasser](https://docs.github.com/en/copilot/concepts/security-governance-and-network-settings/about-cloud-and-local-sandboxes), [agentverktøy](https://docs.github.com/en/copilot/reference/custom-agents-configuration). |
| Fjernstyrt lokal CLI fra mobil eller nettleser | Sesjon og verktøy forblir på den opprinnelige maskinen. Fjernkontroll formidler samtalen. | Ikke presenter localhost-URL som en tilgjengelig mobilskisse. | Preview-tilgang fra den andre enheten er ikke dokumentert av fjernkontroll alene. [Fjernkontroll](https://docs.github.com/en/copilot/concepts/agent-capabilities/agent-powered-workflows-and-operations/about-remote-control). |

## Preflight og registrering

App og CLI har separate sandboxinnstillinger. Loopback og lokale proxyer har
ulike begrensninger på macOS, Linux og Windows. Verifiser derfor skissen i
brukerens nettleser og les innspillskøen fra den runtime som skal behandle den.
Serveroppstart alene er utilstrekkelig. Ikke endre bind-adresse, Origin eller
sandboxpolicy automatisk for å få prøven til å passere.
[Lokale sandboxinnstillinger](https://docs.github.com/en/copilot/how-tos/cloud-and-local-sandboxes/configuring-local-sandbox-settings).

Registrer klient, versjon, operativsystem, harness, lokal/fjern kjøreplass,
pluginrevisjon, faktisk skillkilde, viewport og relevant tillatelsesutfall.
Appversjon og installert CLI-versjon er separate opplysninger. Ikke utled
appens interne runtime fra `copilot` på PATH. Ikke lagre token-URL, privat
sesjonssti, kontoopplysninger eller ekte brukerinnhold i delt testevidens.

Bruk en disponibel konsumentmappe og oppdiktede data. Installer eller oppdater
ikke klienter eller pakker som en del av prøven uten eget mandat. Sjekk faktisk
komponentlasting: CLI-changelog beskriver eksempelvis en rettelse i 1.0.97 for
skills og agents som manglet fra `--plugin-dir`. At en mappe finnes, beviser
ikke at komponentene er aktive.
[CLI-changelog](https://github.com/github/copilot-cli/blob/main/changelog.md).

## Nye klientcase

Disse akseptprøvene må kjøres i den konkrete klienten før adferden kan omtales
som validert der. En stubbet modell eller direkte Node-/nettleserkjøring kan
bevise protokollen, men ikke at en levende klient følger hele arbeidsflyten.

| Prioritet | Case | Observerbart beståttkriterium |
| --- | --- | --- |
| P1 | To arbeidskopier med samme prosjektnavn | Startup-data, skjerm og innspill holdes til riktig økt. Ingen kommentar eller beslutning krysser mellom øktene. |
| P1 | Innsending mens `wait` går | Full tekst og beholdte valg kommer tilbake med riktig skjerm og submission. Svaret vises i skissen etter verifisert revisjon. |
| P1 | Innsending etter timeout eller avsluttet tur | Køen bevares. «Se innspillene» henter den. Tilstedeværelsen lover ikke aktiv behandling etter utløpt frist. |
| P1 | Ny innsending mens forrige runde bearbeides | Ny batch hoppes ikke over. Cursor oppdateres bare for faktisk behandlede runder. Usendte utkast blir ikke gjeldende beslutninger. |
| P1 | Kort shellgrense | Kortere `--timeout` returnerer et lesbart resultat; ved async videreføres samme verktøyjobb. Ingen løs vakt eller løkke uten avtalt slutt innføres. |
| P1 | Nettleseren virker, men CLI-loopback avvises | Ingen feilaktig påstand om aktiv behandling. Klientfeilen forklares konkret og fallback fungerer uten bredere nettverksbinding. |
| P2 | Stopp, vindusbytte og gjenopptakelse | En levende server gjenfinnes korrekt. Stoppet økt får ny URL; gammel midlertidig kø påstås ikke gjenopprettet. |
| P2 | VS Code, delt fane og separat agentfane | Riktig skjerm og viewport inspiseres. Tilstand i den delte fanen forveksles ikke med separat nettlesertilstand. |
| P2 | Mobil fjernstyring og cloud | Ingen preview-tilgjengelighet loves uten faktisk adgang fra brukerens flate. Fallback skjer uten skjult tunnel eller installasjon. |

## App-canvas som prøvd integrasjonsspor

Copilot-appens dokumentasjon beskriver canvas extensions som pluginflater med
handlinger både brukeren og sesjonen kan bruke. En vanlig localhost-side blir
ikke automatisk et canvas. GitHubs eksempel viser derimot en konkret bro fra
eksplisitt UI-handling til `session.send` i den tilknyttede sesjonen.
[Canvas extensions](https://docs.github.com/en/copilot/how-tos/github-copilot-app/working-with-canvas-extensions).

SDK-ens dokumenterte kømodus starter en tur når sesjonen er ledig, og legger
meldingen i kø når den arbeider. Kvitteringen beviser mottak, ikke konsum eller
utført arbeid. Dette gjelder en eksplisitt sesjonsmelding, ikke vilkårlige
UI-endringer. [Kø og styring](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/steering-and-queueing).

Den [avgrensede canvas-prøven](visual-companion-canvas.md) har kontrollert den
installerte SDK-en mot en simulert vert og prøvd grensesnittet i nettleser.
Faktisk appvisning, turkjøring og livssyklus er fortsatt ikke validert.
[ADR 0019](../adr/0019-app-canvas-prove.md) avgrenser forsøket til kode utenfor
pluginpayloaden. Behold dagens server, samlet innsending og avgrenset venting
som portabel kontrakt til en valgfri adapter er prøvd i den konkrete appen.
