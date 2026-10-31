# /kupon od nowa - protokół backtestu (zapisany 2026-10-31 przed obejrzeniem sygnałów)

Dane: `legs.pkl` (nogi wydruków dnia 10-13..10-30, moment decyzji = ostatnia migawka
≥ 30 min przed startem, noga nie zdjęta odczytem), `signals.pkl` (sygnały as-of
z funkcji `bet.sofa.dossier`, cięte na start meczu; liga na 00:00Z dnia), harness
`bt_lib.py` (jedna definicja miar dla wszystkich agentów).

Podział: dev 10-13..10-24 (szukanie), walidacja 10-25..10-28 (wybór), hold-out
10-29..10-30 (10-31 nierozliczony) - raz, po `frozen_rules.json` (sha256 w raporcie);
`bt_lib.load('hold')` odmawia bez tokenu = hash tego pliku.

Miary nogi: lift = trafienie − śr. 1/kurs; **nadwyżka** = lift komórki − lift całej
puli splitu w tym samym paśmie 1/kurs (0,05), ważona nogami komórki (dobra 1,20 vs
zła 1,20); ROI przed podatkiem, pojedyncza po podatku (0,88); CI bootstrap po meczu
(1000), p jednostronne nadwyżki ≤ 0. n < 100 = podejrzenie.

Miary kuponu: wypłata 0,88 × iloczyn (Bet Builder 0,90 × iloczyn), zwrot nogi = 1,00;
ROI po podatku, CI bootstrap po dniu i po kuponie.

Wybór (ustalony z góry):
1. Komórki nóg dev z n ≥ 100: BH (q = 0,10) na p nadwyżki po WSZYSTKICH komórkach
   nóg wszystkich partii (liczba komórek w raporcie).
2. Kandydaci = odkrycia BH z dev; z nich na walidacji (n ≥ 100) 1-3 o najwyższej
   nadwyżce walidacji, której dolna granica CI > −1 pp i punkt > 0. Brak odkryć BH -
   kandydaci = 3 komórki dev o najwyższej nadwyżce z n ≥ 300, oceniane na walidacji
   tak samo; brak komórki z nadwyżką > 0 na walidacji = "przewagi nie ma".
3. Konfiguracja kuponu (nogi, cel, ranking) wybrana na walidacji spośród tych z
   ≥ 30 kuponami: najwyższy ROI po podatku; kontrole (losowy, obecny /kupon,
   pojedyncze) liczone na tych samych dniach.
4. Zamrożenie: `frozen_rules.json` (reguły nóg, ruch ceny, konfiguracja kuponu),
   sha256, potem jedno uruchomienie hold-outu: kandydaci + kontrole.
