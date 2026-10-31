---
status: accepted
date: 2026-10-31
---

# Samme nettsted for lokal appvisning

## Kontekst

Transporten i ADR 0027 brukte `127.0.0.1` for kontrollflaten og `localhost`
for appen. Det krever tredjepartscookies med `SameSite=None; Secure;
Partitioned`. Støtte for `Secure`-cookies over lokal HTTP varierer mellom
nettlesermotorer. Tilgjengelig canvas og en vellykket lokal HTTP-forespørsel
beviser derfor ikke at appen kan brukes. Lokale underdomener er heller ikke
en generell reservevei: vertsappens transportpolicy kan avvise dem.

## Beslutning

Kontrollflaten og appvisningen bruker eksakt `http://127.0.0.1:<port>`, med
hver sin port og origin. Begge lyttere bindes bare til loopback. Appens
transportcookie er vertsbundet, `HttpOnly` og `SameSite=Strict`. Logiske
appcookies får egne navn og `SameSite=Strict`, og bare den aktuelle appens
cookies videresendes til dens låste oppstrøm. Transporten er ikke avhengig
av `Secure`-cookies på HTTP eller partisjonerte tredjepartscookies.

Appproxyer bruker bare portene 20000–29999. Kontrollflater og skrivebeskyttet
skisseinspeksjon bruker aldri dette området, heller ikke ved eksplisitt portvalg
eller når operativsystemet velger en ledig port. En port som har kjørt en
appworker kan derfor ikke senere bli en kontrolladresse. Tildelingen har et
avgrenset antall forsøk og feiler lukket når en egnet port ikke er tilgjengelig.

Kontrollmyndigheten ligger fortsatt utelukkende i en privat headernøkkel,
aktiv dokumentbinding og eksakt Origin/Host-kontroll. Cookies gir ingen
kontrollmyndighet. Forskjellige porter opprettholder origin-grensen for DOM,
sessionStorage og API-er; IP-adressen kan ikke brukes til å slå sammen
originene med `document.domain`. Appen får fortsatt ingen kontrollnøkkel,
filtilgang eller rett til å sende innspill. Worker-kapasiteter beholder sine
egne avgrensninger. Levetid, tilbakekalling og eksplisitt innsending er uendret.

Dette erstatter vertene og cookie-attributtene i ADR 0027, ikke kravet om en
verifisert privat nativekontekst. Cookie-navn er en kompatibilitetsmekanisme,
ikke en sikkerhetsgrense: cookies følger verten på tvers av porter. Appflater
i samme datalager kan påvirke hverandres appcookies, og en gjenbrukt appport kan
arve en appworker. Portområdene beskytter kontrollmyndigheten, men erstatter
ikke isolasjon mellom apper. Åpning i en vanlig delt nettleser er fortsatt ikke støttet.
Kontrolltoken skal aldri flyttes til cookies som en del av denne tilpasningen.

## Verifikasjon og avgrensning

Kontroller appcookies, navigasjon, skjemaer, WebSocket, innspill og gjenåpning
med den faktiske nativeverten og sandkassen på. Negative prøver skal avvise
fremmed Origin, feil Host, dupliserte transportcookies, cookie-basert tilgang
til kontroll-API-er og bruk etter lukking. Prøvene skal også dekke kjørende
forslag i den ekstra rammekjeden og en lagret appworker når en kontrollflate
forsøker å få den gamle appporten.

En browser- eller WKWebView-prøve beviser bare oppsettet som ble kjørt; den
fastsetter ingen minste OS-versjon og erstatter ikke native verifikasjon.
Løsningen skal ikke installere sertifikater, endre klientinnstillinger eller
deaktivere sandbox for å få visningen til å fungere.
