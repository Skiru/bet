# A1: siła ligi jednostki regionalnej startuje od rozgrywek (audyt 2026-10-13)

Przełącznik: `epochs.UNIT_STRENGTH_FROM_PARENT_FROM_UTC`. Kod:
`RatingBook.unit_strength_from_parent`, `RatingBook._strength_entry`.
Skrypt: `scripts/sofa/measure_unit_strength.py` (tylko odczyt).

## Rejestracja (zapisana 2026-10-13 przed uruchomieniem pomiaru)

- Dwa ratingi odtwarzane równolegle na tej samej historii piłki
  (`football_rating.load_history`, jednostki `assign_league_units`), tylko
  metryka `goals_for`: stara reguła (siła nowej jednostki od 0) i nowa (od
  siły rozgrywek-rodzica). Każdy mecz najpierw prognozowany, potem uczy
  (one step ahead) - podział poza próbą w czasie.
- Populacja główna: mecze 2026-06-01..2026-10-12, w których co najmniej jedna
  strona ma domenę będącą jednostką regionalną (`unit_comp[u] != u`) i para
  nie jest LINKED w żadnym z dwóch ratingów; obie strony z >= 5 meczami.
- Metryka główna: log-loss Poissona goli strony przy oczekiwanej z ratingu;
  różnica nowa - stara na mecz (suma dwóch stron), 95% z bootstrapu po meczach
  (2000, ziarno 0). Obok: MSE.
- Próg (O5): włączyć, gdy górna granica 95% < 0. Raportowane też: wszystkie
  mecze ponadligowe (nie LINKED) i wszystkie mecze okna - nowa reguła nie
  może pogarszać ogółu (dolna granica > 0 na wszystkich meczach = nie włączać).

## Wynik (2026-10-13, `data/audit_2026-10-13/a1.json`)

| populacja | mecze | log-loss nowa - stara na mecz [95%] | MSE stara | MSE nowa |
|---|---|---|---|---|
| all | 85995 | -0.00006 [-0.00022; +0.00010] | 2.4740 | 2.4739 |
| cross | 25752 | -0.00028 [-0.00083; +0.00025] | 2.5238 | 2.5233 |
| cross_unit | 7724 | -0.00102 [-0.00291; +0.00081] | 2.8163 | 2.8144 |

Kierunek zgodny z diagnozą (nowa lepsza we wszystkich trzech populacjach), ale
**przedział obejmuje zero** - **zmierzone, nie włączone**
(`UNIT_STRENGTH_FROM_PARENT_FROM_UTC` = None). Następny krok: ten sam test po
replayu ratingu w krzywych (A6), gdzie siła ligi wchodzi także w reszty.
