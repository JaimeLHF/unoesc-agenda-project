# Sondagens da API do Moodle (UNOESC)

Scripts de diagnóstico usados para descobrir como falar com o `on.unoesc.edu.br`
sem scraping de HTML. Só usam a stdlib do Python — não precisam do venv.

```bash
python3 backend/scripts/probes/probe_session.py
```

Todos pedem usuário (`<matrícula>@unoesc.edu.br`) e senha; a senha não aparece
na tela e nada de sensível é impresso.

| Script | Para quê |
| --- | --- |
| `probe_session.py` | Login HTTP direto + lista disciplinas e eventos. **É o que um colega roda** para você saber em 2 min se o app serve para ele. |
| `probe_calendar.py` | Compara as três funções de calendário e mostra os campos de um evento. |
| `probe_contents.py` | Lista as atividades de cada disciplina (quantos `assign`/`quiz` existem). |
| `probe_moodle.py` | Tenta emitir token de Web Service REST. **Não funciona nesta instância** — mantido para documentar o beco sem saída. |

## O que já se sabe (medido em 08/08/2026)

- Moodle **4.5**, tema `unoesc_boost`.
- **Login HTTP puro funciona.** `GET /login/index.php` para pegar o `logintoken`,
  `POST` com usuário/senha → cookies `MoodleSession` + `MOODLEID1_`. Sem portal,
  sem SSO, sem Playwright.
- O `sesskey` sai do `M.cfg` no HTML de qualquer página logada.
- A API interna fica em `POST /lib/ajax/service.php?sesskey=…&info=<fn>` com body
  `[{"index":0,"methodname":"<fn>","args":{…}}]`.

### Funções disponíveis

| Função | Situação |
| --- | --- |
| `core_course_get_enrolled_courses_by_timeline_classification` | ✅ lista as disciplinas |
| `core_calendar_get_calendar_monthly_view` | ✅ **a melhor fonte de agenda** (10 eventos, vs 8 e 2 das outras) |
| `core_calendar_get_action_events_by_timesort` | ⚠️ só o que tem ação pendente — perde os eventos `open` |
| `core_calendar_get_calendar_upcoming_view` | ⚠️ janela curta demais |
| `core_courseformat_get_state` | ✅ lista as atividades de um curso — **devolve string JSON**, precisa de `json.loads` |
| `core_course_get_contents` | ❌ `servicenotavailable` nesta instância |
| `/login/token.php` (REST) | ❌ `servicenotavailable`: `moodle_mobile_app` desligado |

### Detalhes que custaram caro

- O Moodle valida a **senha antes do serviço**: `invalidlogin` = credencial errada,
  `servicenotavailable` = credencial OK e serviço desligado. Não confunda os dois.
- O `dof` (usado pelo portal para gerar o link SSO) vem embutido no `shortname`
  do curso: `28743 - EAD54-12 (DOF_1414949)`. Não precisa raspar o portal.
- Use `timestart`/`timesort` (epoch) dos eventos. O `formattedtime` vem como HTML.
- Varra também **meses passados** no `monthly_view`: prazos vencidos só aparecem lá.
- No `core_courseformat_get_state`, o campo `module` traz o nome **traduzido**
  ("Tarefa", "Questionário"), não o slug. Tire o slug da URL (`/mod/<slug>/`),
  que não depende de idioma.
- Não conte atividade por regex de `<a href>` no HTML do curso: a mesma atividade
  aparece em vários links e a contagem infla (deu 50 `hsuforum` onde havia 19).

### Cobertura do calendário (conta fechada em 08/08/2026, conta do Jaime)

| | Atividades | Eventos gerados |
| --- | --- | --- |
| `assign` | 12 | 12 (`due`) |
| `quiz` | 5 | 10 (`open` + `close`) |
| `hsuforum` (19), `forum` (8), material (33) | 60 | 0 |

O `monthly_view` cobre **100% dos entregáveis** — nenhum evento fica de fora.
Fórum nesses cursos é discussão contínua, sem prazo. Foi verificado que prazo de
fórum, quando existe, **chega** ao calendário (2 eventos `forum` de 2025).

### Limite conhecido

Cursos **presenciais** não têm `assign` nem `quiz` — só PDF e fórum — então o
calendário deles é legitimamente vazio e nenhuma API resolve. O foco do projeto
é EAD.
