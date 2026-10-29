# 0029: Appobservasjon og kjørende forslag i samme verksted

Status: Akseptert

## Bakgrunn

En tilkoblet inspektør og HTTP 200 kan sameksistere med en JavaScript-feil.
En liten HTML-rekonstruksjon kan dessuten miste sammenhengen og oppførselen
som skal vurderes ved endringer i eksisterende sider.

## Beslutning

Designverksted skiller forbindelsen fra observerte appfeil. `read_preview`
ber den aktive visningen om en fersk, begrenset dokumentstruktur og kategorier
for kjøringsfeil. Resultatet er ubetrodd sideinnhold, ikke en instruksjon,
skjermdump eller garanti for korrekt gjengivelse. Feltverdier, HTML, konsolllogg,
feiltekster, nettverkspayload og andre faner inngår ikke. Observasjonen er
midlertidig, har kort tidsfrist og er bundet til gjeldende visning.

`publish_proposal` kan knytte enten en HTML-skisse eller en separat kjørende
appkopi til «Forslag». Det utvider formatvalget i ADR 0027. HTML beholder sin
deklarative sikkerhetsmodell og versjonshistorikk. En appkopi beholder ekte
komponenter og oppførsel; kilden endres med vanlige verktøy bare når arbeid i
den isolerte kopien er avtalt. Referansen skal ikke endres. Canvaset får ingen
kildelesing, kildeeditor, oppstartsmyndighet, kildejournal eller kodeangre.

Begge formater bruker samme faner, innspillsløype og eksakte forslagstilknytning.
Appforslag gjenbruker appskallet. Innbygging tillater bare det konkrete eierrommets
origin, i tillegg til forslagets eksisterende isolerte origin. Kontrollnøkler
forblir utenfor appen. Lagret tilknytning inneholder navn, offentlig startsti,
spørringspolicy og identiteten til innspillsrommet; runtime-adressen lagres ikke.
Gjenåpning trenger en eksplisitt ny lokal forbindelse til samme forslag.
Manglende eller erstattede rom opprettes ikke på nytt.

## Konsekvenser og kontroll

- Velg format etter oppgaven og nødvendig troskap. Bevar hele sidens relevante
  sammenheng; formatvalget skal ikke kreve at designeren skifter verktøy.
- Avhengigheter og låsefil kontrolleres før en installasjon gjenbrukes.
- Sandkassen beholdes. Endringer i prosjektpolicy krever en konkret bekreftet
  plan og ny sandboxed sesjon for verifikasjon; masking slås ikke av automatisk.
- Appforslag har ikke HTML-redigering, versjonskontroller eller senere flytting
  fra midlertidig til lagret rom. Kildekopien må bevares separat ved overlevering.
- Figma bruker den valgte hele siden og tilstandene som kontrollgrunnlag.
- Før utrulling kreves prøve av faktisk app, innspill, synlig forslag, iterasjon
  og gjenåpning i Copilot med sandkassen på. En nettlesersmoke alene oppfyller
  ikke denne porten.
