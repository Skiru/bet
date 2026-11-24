# Boisko neutralne w piłce - pomiar 2026-11-24 (nic nie zmienione)

**Wniosek: nie wdrożono.** Sofascore nie daje flagi boiska neutralnego, a
pomiar na historii nie wykazuje różnicy w przewadze gospodarza z przedziałem
wykluczającym zero. To, co drukuje się, zostaje bez zmian; nie ma przełącznika
w `bet.sofa.epochs`, krzywe nie były ruszane (i tak były dopasowane bez takiego
członu).

## Przypadek

2026-11-15: Godoy Cruz - Tristán Suárez (Sofascore 17488518), finał Primera
Nacional na neutralnym stadionie w Córdobie. SHEET liczył centra z przewagą
gospodarza dla Godoy Cruz; wydrukowano 8 nóg.

## Skąd SHEET bierze przewagę gospodarza

- Piłka: `bet.sofa.football_rating` - centrum strony = stawka ligi x atak x
  obrona; stawka ligi to para `(home_mean, away_mean)` z
  `RatingBook.league_rates` (`expected`: `rates[0]` dla gospodarza, `rates[1]`
  dla gościa). Przewaga gospodarza jest więc w samej stawce ligi, osobno dla
  każdej (rozgrywki, metryki).
- Sporty mierzone: model wyniku (`bet.sofa.score_model`) czyta tę samą książkę
  (udział gospodarza w stawce ligi).

## Czy payload `/event` zna boisko neutralne?

Przejrzane w bazie (tylko odczyt) wszystkie 74 653 zapisane `/event`
(`sofa_event_detail`): klucz `neutralGround` nie występuje w żadnym, w żadnym
sporcie. `hasGlobalHighlights` to flaga skrótów wideo, nie boiska. Jedyny
pośredni sygnał to `event.venue` różne od `homeTeam.venue` - ale
**w meczu 17488518 `event.venue` jest puste** (jest tylko stadion Godoy Cruz w
Mendozie jako `homeTeam.venue`), więc nawet ten sygnał nie złapałby przypadku,
który zgłoszono. W listingach historii (`sofa_listed_event`) pola `venue` nie
ma wcale - neutralności nie da się odtworzyć w replayu historii, na którym
dopasowano krzywe.

## Pomiar (zastępczy sygnał: obiekt meczu != stadion gospodarza)

Mecze piłkarskie zakończone z `sofa_event_detail` (bez walkowerów / wyników
przyznanych, wynik z 90 minut), tylko te, gdzie znane są oba obiekty:
`event.venue` i `homeTeam.venue`. Klasy: `home_ground` (ten sam obiekt),
`neutral` (obiekt nie jest stadionem żadnej ze stron i leży w innym mieście
niż stadion gospodarza), reszta osobno. Różnica bramek gospodarz - gość (GD),
bootstrap po meczach, 4000 losowań, 95%.

| klasa (bez towarzyskich) | n | GD gospodarza | 95% CI |
|---|---|---|---|
| stadion gospodarza | 5 954 | +0.311 | +0.263 .. +0.361 |
| "neutralne" (inne miasto) | 544 | +0.153 | -0.013 .. +0.325 |
| inny obiekt w mieście gospodarza | 398 | +0.291 | +0.085 .. +0.508 |
| obiekt w innym kraju niż stadion gospodarza | 130 | +0.208 | - |
| finał na obcym obiekcie (`roundInfo` "Final") | 29 | -0.103 | - |

- neutralne - stadion gospodarza: **-0.159 [-0.330, +0.014]** - przedział
  obejmuje zero;
- obiekt za granicą - stadion gospodarza: -0.104 [-0.493, +0.295];
- finały: n = 29, za mało na cokolwiek.

Mecze bez pary obiektów (30 153 z 37 111) nie mówią nic o neutralności.
Na mecz "neutralny" przypada ~1,5% piłkarskich szczegółów z parą obiektów;
grupa jest zanieczyszczona (MLS / MLS Next Pro, ligi grające tymczasowo na
cudzych obiektach, Liga Mistrzyń kobiet w turniejach) i nie jest losowa
względem siły drużyn (kto jest "gospodarzem" w finale / turnieju, ustala
losowanie lub terminarz). Punktowo neutralność zmniejsza przewagę gospodarza
mniej więcej o połowę - to **podejrzenie**, nie pomiar spełniający regułę
(przedział nie wyklucza zera).

## Dlaczego nic nie zmieniono

1. Brak flagi w danych: w zgłoszonym meczu payload nie miał nawet obiektu
   meczu - reguła oparta na `venue != homeTeam.venue` nie zmieniłaby tego
   druku.
2. Różnica nie przechodzi reguły "przedział wyklucza zero".
3. Krzywe są dopasowane na replayu historii, w której obiektu meczu nie ma -
   człon neutralny nie byłby replayowalny bez nowej refity (niedozwolonej).

## Co by to zmieniło

Nowy dowód: (a) Sofascore zaczyna podawać obiekt meczu dla finałów / meczów
neutralnych przed startem (sprawdzić `event.venue` w FIXTURE_CHECK dla
finałów pucharowych), (b) większa próba prawdziwie neutralnych meczów
(np. backfill `/event` dla finałów i turniejów reprezentacji) z CI
wykluczającym zero. Wtedy: przełącznik w `epochs` od następnego dnia 00:00Z,
marker wiersza dla `rebuild_plan`, stawka ligi (home + away) / 2 dla obu stron.

Skrypt pomiaru: jednorazowy, tylko odczyt bazy (`?mode=ro`), nie dołączony do
repozytorium; definicje klas jak wyżej.
