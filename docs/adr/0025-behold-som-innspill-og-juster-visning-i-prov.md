---
status: accepted
date: 2026-10-25
---

# Behold som innspill og «Juster visning» i «Prøv»

Delvis erstatter [ADR 0018](0018-deklarerte-justeringer-og-beholdte-valg.md)
for hvordan en del beholdes, og bygger på
[ADR 0023](0023-prosjektlagret-designrom.md).

## Kontekst

Designverkstedet hadde to måter å bevare noe på. Et lagret felt fra
«Rediger» sperrer motstridende overskriving til designeren tillater senere
endring. «Behold dette» i «Juster» lagret i tillegg en egen beslutning som fulgte
alle senere runder, hadde egne konflikter mellom faner og egne knapper for å
slippe den igjen. Gjennomgangen av grensesnittet fant at de to mekanismene ikke
var forutsigbare for designere, og at et ønske om å beholde en del i praksis er
en bestilling til agenten, ikke en låsing.

«Juster» lå samtidig under «Endre», selv om den bare prøver deklarerte valg
lokalt og ikke endrer skissen. Sammenligning av varianter var allerede flyttet
til «Vis» i «Prøv».

## Beslutning

«Behold denne delen» lagrer et vanlig punktinnspill på delen. Teksten starter
med «Behold denne delen.», eventuelt fulgt av designerens merknad, og den
lukkede `context`-strukturen fra ADR 0020 navngir variant, del og valgte
verdier. Innspillet sendes, besvares og vises som andre innspill. Agenten skal
beholde delen i neste versjon og ikke endre den senere uten et nytt innspill
som ber om det.

Beholdte valg fjernes helt: lagring (`decisions`, `submittedDecisions` og
`decisions` i rundene), server-API, CLI-kommandoen `release`, kortene i
innspillskurven og sperren mot redigering. De kom inn med det prosjektlagrede
designrommet og er aldri sluppet, så ingen brukerdata må leses eller migreres.
Lagrede felt fra «Rediger» er dermed den eneste varige føringen, og de slippes
med «Tillat senere endring».

«Juster» blir «Juster visning» og flyttes til «Vis» i «Prøv», sammen med
«Sammenlign varianter». Når panelet er åpent, står Vis-knappene i panelets
tittelrad. «Endre» samler «Be om endring» og, i et prosjektlagret rom med
redigerbar skisse, «Rediger». Et innspill som skrives mens «Rediger» har
ulagrede endringer, gjelder den lagrede versjonen; grensesnittet sier dette, og
de ulagrede verdiene blir stående i «Rediger».

## Konsekvenser

Designeren har én varig bevaring å forholde seg til: lagrede felt. Et ønske om
å beholde en del er synlig i kurven og i runden, men håndheves ikke mekanisk.
Konflikthåndteringen for samtidige «Behold dette» fra flere faner forsvinner;
to faner gir i stedet to separate innspill. Datamodell, API og agentveiledning
blir mindre.

Agenten må lese «Behold denne delen.» med `context` som et krav for neste versjon
og senere versjoner til et nytt innspill sier noe annet. Overleveringer
behandler slike innspill som andre innsendte innspill. Et rom lagret av en
uutgitt bygg med beholdte valg avvises ved åpning som ugyldig tilstand.

Lokal utprøving er samlet i «Prøv», og alt i «Endre» lagrer noe: et innspill i
kurven eller en ny skisseversjon. Ingen ny tjeneste, kø, filsynkronisering eller
skrivevei innføres.
