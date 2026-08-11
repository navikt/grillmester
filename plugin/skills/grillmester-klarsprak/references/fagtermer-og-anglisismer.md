# Fagtermer, anglisismer og teksttyper

Bruk denne referansen som spørsmåls- og eksempelbank. Consumerens dokumenterte
språkpolicy og domenespråk har forrang.

## Finn riktig term

1. Bevar kodeidentifikatorer, protokollnavn, produktnavn og API-felter.
2. Bruk consumerens glossary eller språkpolicy for domeneord.
3. Se etter konsekvent bruk i vedlikeholdt dokumentasjon.
4. Hvis norsk og engelsk variant konkurrerer uten en regel, spør brukeren og
   vær konsekvent i artefakten.

Tekniske ord som ofte beholdes på engelsk i norsk utviklertekst inkluderer
endpoint, payload, request, response, token, claim, consumer, producer, topic,
schema, runtime, framework, deploy, rollback og commit. Dette er eksempler, ikke
en universell fasit.

Norske ord er ofte naturlige for feilsøking, vedlikehold, tilgjengelighet,
kodegjennomgang, avhengighet, kø, melding, validering og oppslag. Et etablert
domenespråk kan velge annerledes.

## Sammensatte ord

Bruk som regel bindestrek når en engelsk fagterm inngår i et norsk sammensatt
ord: Kafka-topic, token-validering, deploy-steg og GitHub-repository. Unngå
særskriving når uttrykket fungerer som ett norsk ord.

## Vanlige anglisismer

| Formulering | Klarere norsk når betydningen passer |
|---|---|
| adressere et problem | løse, fikse, ta tak i |
| ta eierskap til | ha ansvar for |
| har du noen input? | har du innspill? |
| shippe | levere, sende ut |
| reviewe | gå gjennom, se over |
| tracke | følge med på, spore |
| aligne | samkjøre, bli enige |
| være på samme side | være enige |
| per dags dato | nå, i dag |

Ikke gjør mekaniske utskiftninger. «Deploy» kan for eksempel være et presist
fagord i consumerens tekst, mens «rulle ut» passer bedre for en bred målgruppe.

## Tone per teksttype

| Teksttype | Spørsmål før redigering |
|---|---|
| ADR | Hvilket språk, format og statusord krever repositoryet? |
| README | Hva trenger en ny leser først, og hvilke fakta er verifisert? |
| Loggmelding | Hvilket loggspråk og hvilke søkbare felter bruker tjenesten? |
| Feilmelding | Hva gikk galt, og hva kan mottakeren faktisk gjøre? |
| PR-beskrivelse | Hva endres, hvorfor og hvordan er det verifisert? |
| Commit-melding | Hvilken lokal konvensjon gjelder? |

## Kilder

- [Språkrådets klarspråksider](https://sprakradet.no/Klarsprak/)
- [ISO 24495-1 hos Språkrådet](https://sprakradet.no/klarsprak/kunnskap-om-klarsprak/iso-standard-for-klarsprak/)
- [Digdirs klarspråkveiledning](https://www.digdir.no/klart-sprak/ny-veileder-om-klart-sprak-i-utvikling-av-digitale-tjenester/3603)
- [Termportalen](https://www.termportalen.no/)
