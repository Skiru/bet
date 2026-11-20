# Przewaga nad ceną - protokół (zamrożony 2026-11-20 przed uruchomieniem)

Pytanie: czy i gdzie pewność (`confidence`) wydrukowanej nogi bije cenę
Superbetu bez marży POZA PRÓBĄ - krawędź i CLV. Tylko pomiar; nic nie
zmienia wydruku. Skrypt: `scripts/sofa/measure_price_edge.py` (odmawia
pracy, gdy sha256 tego pliku różni się od stałej w skrypcie).

## Dane (wyłącznie pliki dnia, baza nieużywana)

- **Nogi** = pozycje pojedyncze wydrukowane na kuponie dnia, ocenione przez
  księgę: `runs/sofa/<d>/13_results.json` `legs`, status `won` / `lost`
  (zwrot, `unknown` - poza pomiarem, liczone osobno). Kurs wzięty = `odds`
  z 13_results (cena, po której księga rozlicza).
- Pola nogi: `11_coupon.json` `singles` (każdy sport), a gdy dnia nie ma
  (10-17, 10-18, 10-24, 10-25, 10-31, 11-01, 11-07, 11-08, 11-14 - pliki
  skasowane 11-19): piłka / tenis z `08_confidence.json` `legs`, sporty z
  `08_confidence_sports.json` `legs` (tylko nogi ostatniej przebudowy -
  braki liczone i podane).
- Dni: 10-13..11-19 (13_results istnieje). **Dev = 10-13..11-09**,
  **hold-out = 11-10..11-19** (10 dni). Epoki są w obu splitach łączone
  (pytanie dotyczy liczby obok ceny, nie wersji modelu) - raport to mówi.

## Cena bez marży przy wydruku (`fair_p`)

- Piłka / tenis, noga dwustronna: `market_p` nogi (de-vig power po
  szczeblach drabinki, jak w CONFIDENCE), przeskalowane do kursu wziętego:
  `fair_p = market_p × offered_odds / odds`.
- Sporty (hokej, koszykówka, siatkówka, CS2): de-vig power pary
  odtworzonej z `overround` nogi: druga strona = `1 + overround − 1/odds`
  (`engine.devig`). Tylko gdy linia jest dwustronna: jej oceniony wpis w
  `settled.json` sportu nie ma `group_odds` o > 2 stronach.
- **Bez `fair_p`** (piłkarska noga jednostronna, sport wielostronny / bez
  wpisu, overround brak): krawędź mierzona **względem 1/kurs** (surowo -
  1/kurs > cena bez marży, więc taka komórka jest trudniejsza do zdania).
  Te nogi tworzą osobne komórki (`priced = raw`), nigdy nie mieszane z
  `fair`.

## Miary nogi

- `edge = wygrana(1/0) − fair_p` (albo − 1/kurs dla `raw`).
- `roi = kurs × wygrana − 1` (przed podatkiem; po podatku 12% noga musi mieć
  p × kurs ≥ 1/0,88 = 1,136 - podawane obok, nie testowane).
- `clv = odds × p_close − 1`, `p_close` = de-vig power pary zamknięcia
  (`bet.sofa.clv.two_way_close`, grupa > 2: `group_close`); zamknięcie =
  rekord 3-30 min przed startem (`clv.is_close`): piłka / tenis
  `closing.jsonl` (wariant `official`, najnowszy rekord z ceną w oknie, jak
  `audit_clv.closing_rows`), sporty - oceniony wpis `settled.json` (dzień i
  dzień następny, klucz jak `audit_clv.SPORT_DIRS`). Bez pary zamknięcia -
  brak CLV (liczone).
- `beat` = kurs wzięty > kurs zamknięcia (opisowo).

## Komórki (rodziny; każda komórka w obu splitach)

Wymiary: `sport`, `md` = market|DIR (piłka / tenis `market|direction`,
sporty `family|side`), `comp` = rozgrywki (`competition`), `band` = pasmo
`d = confidence − 1/odds`: `<-0.05`, `-0.05..-0.02`, `-0.02..0`, `0..0.03`,
`0.03..0.06`, `>=0.06`; `tts` = godziny od pierwszego wydruku do
startu: `<1`, `1-3`, `3-6`, `6-12`, `>=12`; pierwszy wydruk = znacznik
czasu najwcześniejszego `printed/<ts>.json`, którego `singles` zawiera nogę
(klucz `coupon_results.key_of`), a gdy dnia bez `printed/` - `printed_at_utc`
nogi; brak obu = poza rodzinami z `tts` (sprawdzone na dniach dev 10-20,
11-05, 11-08 przed zamrożeniem: samo `printed_at_utc` pokrywało 0-13% nóg); `over` = confidence > fair_p (tak / nie; tylko `fair`).

Rodziny: F1 sport · F2 sport×md · F3 sport×comp · F4 sport×band ·
F5 sport×tts · F6 sport×md×band · F7 sport×md×tts · F8 sport×comp×band ·
F9 sport×over · F10 sport×md×over · F11 sport×comp×over.
Każda komórka dodatkowo dzielona po `priced` (`fair` / `raw`).

## Reguła (zamrożona)

1. **Kandydat** (tylko dev): n_dev ≥ 300 nóg i dolna granica 95% CI miary
   na dev > 0.
2. **Zdany** (hold-out, raz): kandydat z n_hold ≥ 300 i dolną granicą CI
   na poziomie 1 − 0,05/k > 0, k = liczba kandydatów z n_hold ≥ 300
   (Bonferroni). Osobno dla miary `edge` i miary `clv` (CLV: n liczone na
   nogach z CLV).
3. **Skan opisowy**: każda komórka hold-outu z n ≥ 300 - p jednostronne z
   bootstrapu (odsetek prób ≤ 0), Benjamini-Hochberg q = 0,10; podana
   liczba przetestowanych komórek. Skan nie zmienia werdyktu z pkt 2.
4. Pytanie 3: rodziny F9-F11 (`over = tak`) - czy CLV > 0 (reguła 1-2 na
   mierze `clv`) i korelacja edge-CLV na nogach (opisowo).
5. CI: bootstrap po meczach (`sofascore_event_id`), 2 000 prób, ziarno 20261120,
   percentylowy; średnia ważona nogami.

## Otwarcie

Kurs otwarcia nie jest zakładany: skrypt raportuje, co jest (pierwsza
migawka SHADOW / CS2 dla nóg sportów; piłka / tenis - `04_offer.json` jest
nadpisywany, pierwszy wydruk = najwcześniejsza znana cena). Ruch
otwarcie → wydruk → zamknięcie tylko opisowo, bez testu.

## Wynik

„Nic nie przeszło” jest wynikiem. Żadna komórka nie zmienia kuponu; zdana
komórka = kandydat do testu naprzód zarejestrowanego w
`config/sofa_test_registry.json`, przełącznik tylko na sygnał operatora.
