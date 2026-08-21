---
description: Leses når du trenger konkrete før/etter-eksempler på språkvask av norsk teknisk tekst, PR-beskrivelser, README og API-respons.
---
# Før og etter

Generiske eksempler på redigering fra AI-tung eller stiv tekst til klarspråk.
Tilpass fagtermer og språk til consumerens dokumenterte praksis.

## AI-språk → rett på sak

```
❌ Det er viktig å påpeke at en eventdrevet arkitektur representerer et
   betydelig skritt fremover, og spiller en avgjørende rolle i moderne
   skyinfrastruktur.

✅ Tjenesten konsumerer meldinger fra Kafka og oppdaterer databasen.
```

## Substantivsyke → verb

```
❌ Gjennomføring av en evaluering av ytelseskarakteristikkene til de ulike
   databasealternativene er nødvendig.

✅ Vi må teste ytelsen til de ulike databasene.
```

## Feiloversatt fagterm → behold engelsk

```
❌ Vi må rulle tilbake avbildet og opprette en ny hemmelighet i navnerommet.

✅ Vi må gjøre rollback på imaget og opprette en ny secret i namespacet.
```

```
❌ Vi fant en grensetilfelle i utrullingsflyten som krever en hastefiks.

✅ Vi fant en edge case i deploy-flyten som krever en hotfix i prod.
```

## Anglisme → naturlig norsk

```
❌ Vi må adressere dette problemet og ta eierskap til prosessen for å
   levere en løsning som er på linje med forventningene.

✅ Vi må fikse dette. Teamet har ansvar for å finne en løsning.
```

## For stiv tone → kollegial

```
❌ Det benyttes en hendelsesdrevet arkitektur der meldinger publiseres til
   en meldingskø for videre prosessering.

✅ Vi bruker en eventdrevet arkitektur. Meldinger publiseres til Kafka og
   plukkes opp av consumerne.
```

## API-respons → klarspråk

```
❌ call.respond(BadRequest, "Operasjonen kunne ikke gjennomføres grunnet
   manglende obligatoriske feltverdier.")

✅ call.respond(BadRequest, "Mangler fødselsdato. Send 'fodselsdato' på
   formatet ÅÅÅÅ-MM-DD.")
```

## README → rett på sak

```
❌ Dette prosjektet representerer et innovativt verktøy som muliggjør effektiv
   håndtering av meldinger. Det er utviklet med tanke på å sette brukeren i sentrum.

✅ Tar imot bestillinger fra saksbehandlingssystemet og publiserer status når
   behandlingen er ferdig.
```

## PR-beskrivelse → konkret

```
❌ Denne PR-en adresserer behovet for å implementere en mer robust og helhetlig
   løsning for autentisering som tilrettelegger for en sømløs brukeropplevelse.

✅ Bytter fra manuell token-parsing til token-validation-ktor med TokenX.
   Forenkler auth-flyten og fikser bug der utløpte tokens ikke ble avvist.
```

## Unødvendig oppsummering → kutt

```
❌ Vi har nå gjennomgått de ulike aspektene ved migrasjonen. Som vi har sett, er
   det flere viktige hensyn å ta. Oppsummert kan man si at en vellykket migrering
   krever grundig planlegging.

✅ (Kutt hele avsnittet. Leseren har allerede lest det du oppsummerer.)
```
