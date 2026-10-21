# RESOLVE: pudło liczy się tylko w swoim dniu (2026-10-21)

Przełącznik `epochs.ENTITY_MISS_PER_DAY_FROM_UTC` = **2026-10-21 09:20Z**
(operator: „rob wszystko zeby zaczelo dzialac od dzisiaj”). 10-21 jest dniem
mieszanym (grupa ledgera „10-21 mieszany”); nogi wydrukowane wcześniej zostają.
Tą samą godziną przesunięto `SQUAD_SEARCH_RETRY_FROM_UTC` (było 10-22 00:00Z).

## Problem

Nazwa, której RESOLVE nie znalazł, trafiała do `sofa_entity_miss` i nie była
szukana przez 7 dni (`entity_miss_ttl_min` = 10080). Pudło jest faktem o dniu,
w którym je zapisano — następny mecz tej drużyny mógł już być na Sofascore.

## Pomiar (tylko odczyt, 2026-10-21)

- Piłka, pozycje tablic 10-13..10-20 bez meczu i bez żadnej znanej strony: 127.
  Powtórka RESOLVE na kopii bazy z wyczyszczonymi pudłami: **11** z nich to
  nazwy zablokowane starszym pudłem, choć mecz był na Sofascore (np. Tripoli SC
  · Al Akhaa Ahli Aley → AC Tripoli – Al-Akhaa Al-Ahli 17182512, pudła z 10-08
  i 10-09; CS Hammam-Lif · JS Omrane 17314079; FK Istiklol · Al Arabi 16875760).
- Późne przejście RESOLVE (10-21 08:48Z) nie dopytało dwóch meczów ITF, które
  Sofascore wystawił po porannym RESOLVE (Ravasio · Bouchelaghem, Sharma ·
  Aggarwal): pudła z 10-20 05:40Z. Na kopii bazy bez tych pudeł oba się
  dopasowują (08:40Z).

## Reguła

- RESOLVE: pudło blokuje tylko, gdy zapisano je w dniu (UTC) startu meczu.
- Późne przejście (`run_late_resolve.py`): także pudło starsze niż
  `late_resolve.LATE_LISTING_TTL_MIN` (30 min) nie blokuje — tak jak listingi.
- Nazwa zweryfikowana: bez zmian (pudło jej nie blokuje od 2026-10-01).
- Koszt: jedno wyszukanie na niedopasowaną nazwę na dzień (lista luk, ok. 30 nazw).

## Testy i bramki

`tests/sofa/test_resolve_miss_per_day.py` (pudło z poprzedniego dnia nie
blokuje, z dnia meczu blokuje, późne przejście dopytuje pudło starsze niż
30 min, przełącznik wyłączony = 7 dni). Pełne bramki w commicie.

**Nie sprawdzono jeszcze:** ilu meczów i nóg reguła doda w kolejnych dniach;
pierwsze uruchomienie to przebudowa 10-21 po 09:20Z.
