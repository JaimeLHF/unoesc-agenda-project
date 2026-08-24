# Agenda UNOESC — contexto do projeto

App que reúne prazos, provas e webconferências de todas as disciplinas do Moodle
da UNOESC numa agenda só. FastAPI + SQLite no backend, React + TypeScript + Vite
no frontend, tudo num container só no Fly.io (`unoesc-agenda.fly.dev`).

Projeto independente feito por alunos — **não é serviço oficial da UNOESC**, e
isso precisa continuar visível na interface.

## Comandos

```bash
make dev      # backend em :8880 + frontend em :5180
make test     # teste de isolamento multi-tenant (critério de aceite)
make deploy   # backup do banco de produção + test + fly deploy
```

Frontend: `cd frontend && npx tsc --noEmit && npm run lint && npm run build`.

## Decisões que não são óbvias no código

**A senha do Moodle é guardada cifrada no servidor.** Não é descuido: o cliente
precisa relogar sozinho quando a sessão do Moodle expira. O raciocínio inteiro
está em `backend/app/crypto.py`. Substituir isso por token de web service é o
item de maior impacto do `docs/PLANO_PUBLICO.md` — o pedido pronto para a TI da
UNOESC e o que muda no código estão em `docs/TOKEN_WEB_SERVICE.md`.

**O semestre de uma disciplina sai do `startdate`, nunca do `enddate`.** No
Moodle da UNOESC o `enddate` é quando a *sala* fecha, meses depois do
componente acabar — Engenharia de Software terminou em 12/07/2026 e a sala só
fecha em 10/09. O `startdate` vem 7 dias antes do início oficial (é quando o
acesso libera), então `academicTerm()` soma esses 7 dias e olha o mês. Sem isso
a lista mistura 2026/1 com 2026/2, que foi o bug de 18/08/2026.

**As disciplinas do semestre que ainda não começou não aparecem** — o Moodle só
matricula 7 dias antes. Não é falha do app.

**Nota vem do HTML, não do AJAX.** As funções de nota do `service.php`
respondem `servicenotavailable` nesta instância. O total por disciplina sai de
`/grade/report/overview` (uma requisição para todas) e o boletim item a item de
`/grade/report/user`. Situação acadêmica ("Aprovado") o Moodle não guarda: o
app deriva do corte em `PASSING_GRADE`, e só para disciplina encerrada.

**O aluno fica conectado e não é mais perguntado sobre isso.** O token vivia
no `sessionStorage` e a sessão do servidor durava 8h: no iPhone, fechar o app
instalado é fechar a aba, então toda abertura caía no login. Virou
`localStorage` com TTL de 30 dias e uma caixa "Manter conectado neste
aparelho" marcada por padrão — e nem os 30 dias nem a caixa se sustentaram:
quem passa um recesso sem abrir volta em fevereiro e cai no login, e a caixa
só existia para o computador de laboratório, onde o botão "Sair" do perfil já
resolvia. Hoje o token é sempre `localStorage` e `SESSION_IDLE_TTL`
(`session.py`) é `None` — a sessão acaba em "Sair", em `revoke_for_user` ou
numa `SESSION_SECRET` nova, que derruba todas de uma vez porque a senha
guardada deixa de decifrar. Voltar a expirar é trocar o `None` por um
`timedelta`; `get()` e `purge_expired()` já tratam os dois casos. Contra XSS
`localStorage` e `sessionStorage` valem o mesmo; a proteção real seria cookie
httpOnly, anotado em `frontend/src/services/api.ts`. A notificação push nunca
dependeu dessa sessão: ela usa a senha cifrada da própria inscrição.

**O assistente se chama Lumi e é acessado por um botão flutuante.** O acesso
ficava na barra de cima, junto de Atualizar — onde o aluno passa uma vez ao
abrir o app e não volta mais. A pergunta que Lumi responde ("por onde eu
começo?") nasce olhando a agenda, então o botão vive fixo no canto inferior
direito (`frontend/src/components/AssistantFab.tsx`), em toda tela menos a
dele. O prompt tem teto de 5 linhas por resposta: o aluno lê isso no celular,
entre uma aula e outra.

**O modelo do Gemini é um alvo móvel.** Em 18/08/2026 a primeira pergunta em
produção voltou 404: o Google aposentou o `gemini-2.0-flash` e a própria
resposta mandou usar `gemini-3.6-flash`. O nome vive no secret `GEMINI_MODEL`
do Fly (e no `backend/.env` local), com o padrão do código em `assistant.py` —
os três precisam andar juntos. A chave está configurada em produção desde
18/08/2026; sem ela o `/api/health` acusa `ai_key_optional: false` e o botão da
Lumi não é desenhado.

**As conversas com a Lumi ficam no `localStorage`, não no servidor.** Guardar
no banco custaria tabela, endpoint e mais uma entrada no teste de isolamento
para um dado que só interessa a quem escreveu. A chave inclui a matrícula
(`lumi:conversas:<username>`) porque a máquina pode ser compartilhada — no
laboratório o próximo aluno abre o mesmo Chrome. Ver
`frontend/src/lib/lumiConversas.ts`.

**O enunciado da atividade é lido, mas só para a tela.** `activity_content()` já
foi apagado uma vez, porque alimentava um assistente que respondia provas.
Voltou em 14/08/2026 com destino único: a página da atividade. `assistant.py`
monta o contexto com data, disciplina e título, e só. Não passe o enunciado para
ele.

**A agenda não abre com o cache.** Espera o Moodle responder mostrando só o
esqueleto. Meia agenda velha, numa tela de prazos, é pior que nenhuma — o aluno
não tem como saber qual metade está velha. O cache só entra se o Moodle estiver
fora, e a tela avisa.

**Login automático no Moodle é impossível.** O navegador não aceita cookie de
outro domínio; a única saída seria um plugin instalado pelo admin da UNOESC. Não
tente de novo.

**Curso presencial não cadastra atividade no Moodle — os prazos estão dentro
do PDF.** Medido em 18/08/2026 numa conta de Medicina Veterinária: 4
disciplinas, 58 `resource`, 4 fóruns de tira-dúvidas e **zero** eventos de
calendário. O quadro de avaliações estava numa lâmina do PDF de apresentação.
`backend/app/schedule_pdf.py` garimpa esse texto, e é **plano B**: só roda para
a disciplina que não produziu nenhum evento de calendário, então para quem
cursa EAD custa zero requisição. Data lida assim chega ao frontend com
`source: "pdf_curso"` e a semana marca com o selo "PDF" — data interpretada por
regex não vale o mesmo que data cadastrada pelo professor, e o aluno precisa
saber a diferença. Sem OCR: lâmina escaneada não tem texto e fica de fora.

**A agenda avisa quando o professor muda a data.** Antes ela trocava o dia em
silêncio, e quem já tinha se programado para a data velha não tinha como
perceber. O banco guarda `previous_date` no evento; o selo diz "Adiado" ou
"Antecipado" e expira em `DIAS_AVISO_MUDANCA` (14 dias) — ficar até a entrega
faria o aviso virar paisagem. Isso só funciona porque `stable_key` sobrevive à
troca de data: vem do id do Moodle, não do conteúdo.

**O aviso de semana cheia é uma frase, não um gráfico.** O painel "Panorama"
já foi construído e descartado neste projeto, então a carga da semana aparece
como uma linha no topo da agenda e um selo no cabeçalho da visão por semana.
Dois recortes diferentes de propósito: o topo conta os **próximos 7 dias** (na
quinta-feira o que importa é o que vem, não o que sobra até domingo) e o selo
conta a **semana do calendário** que está na tela, porque ali o aluno navega
entre semanas. O corte é 3 compromissos ou 2 provas (`LIMITE_SEMANA_CHEIA` em
`frontend/src/lib/semana.ts`) — abaixo disso apareceria quase toda semana e
viraria paisagem. Concluído não pesa.

**A agenda avisa que saiu nota.** Mesma máquina do prazo alterado: a nota
anterior fica em `previous_grade` e o selo expira em `DIAS_AVISO_MUDANCA`. Duas
regras que não são óbvias — disciplina vista pela primeira vez nunca vira aviso
(quem se cadastra no meio do semestre não quer as notas velhas como novidade),
e **scrape que volta sem nota não sobrescreve a nota guardada**: o relatório do
Moodle já respondeu `servicenotavailable` nesta instância, e apagar seria
silencioso. O `upsert_subjects` trata os dois casos, e o teste de isolamento
cobre o segundo.

**"Novidades na sala" é o único sinal que o curso presencial emite.** Lá não há
evento de calendário nenhum, só arquivo — então o app registra o inventário da
sala (`course_items`) e marca o que apareceu desde a última visita. O que já
estava lá no primeiro acesso entra como `baseline` e nunca é anunciado, senão a
tela nasceria pedindo para ser ignorada. Custa uma chamada AJAX por disciplina
no `run()`, reaproveitada pelo garimpo de PDF. Some sozinho em
`DIAS_MATERIAL_NOVO` (7 dias) — sem botão de "marcar como visto", que seria
mais uma tabela e mais um endpoint.

**O peso da avaliação sai do PDF, não do Moodle.** O quadro do curso presencial
traz "– Peso: 4" no fim da linha; isso já era apagado do título e agora vira
campo (`weight`). O calendário do Moodle não tem equivalente, então prazo
cadastrado pelo professor não mostra peso — e isso é correto, não falta de dado.

**O app é instalável na tela inicial, e o service worker nunca toca em
`/api`.** O manifest e o `frontend/public/sw.js` foram escritos à mão, sem
plugin de PWA: o que uma biblioteca traria de útil é justamente o que este app
não pode usar. Guardar resposta de API desfaria em silêncio a regra de que a
agenda espera o Moodle — o cache só entra quando o backend decide, e a tela
avisa. O service worker guarda só a casca (HTML, bundle, CSS, ícone) e é
registrado apenas em `import.meta.env.PROD`, senão ele serviria por cima do hot
reload do Vite e toda alteração pareceria não ter efeito. O `.webmanifest`
precisa do `mimetypes.add_type` em `main.py`: sem ele o Chrome ignora o
manifest sem erro nenhum na tela. O QR que leva ao endereço é um SVG estático
em `public/qr-instalar.svg`, gerado uma vez fora do projeto (`segno` num venv
descartável) porque o endereço não muda — biblioteca de QR no bundle seria
pagar JavaScript para desenhar um arquivo constante. Ele aparece no login e no
perfil, e some abaixo de 640px: quem já está no celular não aponta a câmera
para a própria tela. Loja de aplicativo não entra nessa conta —
ver o próximo passo em `docs/PLANO_PUBLICO.md`.

**O `.ics` é buscado pelo servidor do Google, não pelo aluno.** Por isso
`/calendario/{token}.ics` fica fora de `/api` e sem sessão: a chave da URL é a
credencial inteira, só de leitura e trocável num clique. Ele serve o cache —
buscar no Moodle exigiria a senha e demoraria mais do que o cliente espera.

**A notificação no celular guarda a senha fora da sessão.** Este é o custo do
recurso, e está escrito na tela de opt-in: para avisar "saiu nota" com o app
fechado, o servidor entra no Moodle sozinho às 7h, 13h e 19h — quem dispara é o
relógio e não uma visita, então não há token de navegador nenhum em jogo nessa
hora. Quem liga os avisos guarda a senha cifrada junto da inscrição
(`push_subscriptions.password_enc`), e desligar apaga na hora. Três horários e
não um por hora: cada rodada é um login no Moodle da UNOESC por aluno inscrito.
Os textos vivem em `push.py`, o relógio em `scheduler.py`.

**O `fly.toml` deixou de escalar a zero por causa disso.** Disparo das 7h nasce
do relógio, não de uma visita, e máquina suspensa não olha relógio. Quem quiser
a conta de volta perto de zero: `min_machines_running = 0` mais o secret
`PUSH_CRON_TOKEN` e um cron externo batendo em `/api/push/run`. Está anotado no
próprio `fly.toml`.

**O convite de notificação volta a cada sessão, e a saída é o terceiro
botão.** "Deseja receber notificações de compromissos?" abre a agenda enquanto
o aluno não decidir — "Agora não" morre com a aba (`sessionStorage`) e "Não
mostre isso novamente" fica no aparelho (`localStorage`). Preferência de
aparelho e não de conta: dá para querer o aviso no celular e não no computador
do laboratório. A chave inclui a matrícula, como no `lumiConversas`. Desligar
os avisos pelo perfil devolve o convite, senão quem apertou "não mostre mais"
ficaria sem caminho de volta. Ver `frontend/src/lib/avisoNotificacao.ts`.

**Notificação demais queima o canal.** No Android, bloqueio de notificação não
se recupera — o navegador não pergunta de novo. Por isso são no máximo três por
dia, com conteúdo diferente em cada uma, e o `tag` faz o aviso novo substituir o
anterior do mesmo tipo em vez de empilhar.

**O `.env` do backend não era lido.** `python-dotenv` estava nas dependências
mas ninguém chamava: em desenvolvimento o arquivo era decorativo e as chaves só
valiam exportadas na mão. O `main.py` agora carrega com `override=False`, para
que os secrets do Fly continuem mandando em produção.

**Matrícula sozinha e e-mail inteiro são a mesma conta.** O Moodle aceita as
duas formas, e o app guardava exatamente o que o aluno digitou — então a mesma
pessoa podia ter duas contas, com duas agendas e duas inscrições de
notificação, sem nenhum sinal na tela. Aconteceu em produção (`395763` ao lado
de contas com domínio). `normalizar_login` em `moodle.py` completa
`@unoesc.edu.br` **só quando o login é todo numérico**: existe login no formato
`nome.sobrenome`, e inventar domínio para ele quebraria quem entra hoje. Vale
antes do rate limit também — as duas formas são a mesma pessoa tentando a
mesma senha. As contas antigas são migradas no `init_db`; quando as duas
formas já existem, nenhuma é alterada, porque juntar duas agendas exigiria
decidir de quem é cada "concluído".

**O nome do aluno é guardado só para o painel.** O login é matrícula, e uma
lista de números não diz quem entrou. O `full_name` chega pelo `/api/profile`
— a mesma visita que já busca o cadastro no Moodle para a barra do app — e é
gravado só quando muda; nome vazio nunca apaga o que já está lá, porque o
Moodle já respondeu sem cadastro em falha temporária. Ele não autentica nada e
não aparece para outro aluno: quem ainda não abriu o app aparece como "sem
nome ainda" no painel.

**O painel do dono é a única tela que olha todos os alunos.** Existe porque
"alguém está usando isso, e está funcionando?" não tinha resposta sem abrir um
terminal. Fica em `/admin`, lê ao vivo e se atualiza sozinho a cada minuto —
painel que mostra número velho sem avisar é pior que não ter painel. Três
decisões que não são óbvias: o acesso é por **matrícula** no secret
`ADMIN_USERNAMES` (sem ele a rota não existe), quem não é dono recebe **404 e
não 403** — um 403 confirmaria que há um painel ali — e o endpoint **não
devolve credencial nenhuma** (senha cifrada, token, chave do .ics, endpoint de
push), o que o `test_isolamento.py` verifica lendo o JSON inteiro. As métricas
de servidor (p50/p95, rotas, falhas) vivem na memória do processo em
`observability.py`: zeram a cada deploy, e a tela diz desde quando conta.
Guardar isso em banco custaria uma escrita por requisição para um dado que
ninguém consulta sobre o mês passado. Existe também o `make admin`, que baixa
o banco e monta o mesmo panorama num HTML local — é o caminho de quando o
próprio servidor está fora do ar.

**Duas coisas já foram construídas e removidas a pedido do Jaime**, e não devem
voltar sem ele pedir: o painel de gráficos "Panorama" (commits `f747f84`,
`36f8309`, `afc6fce`) e o lembrete por e-mail antes do prazo (`f62cc9d`) — a
UNOESC já avisa dos prazos por e-mail, e mais um aviso no mesmo canal é ruído.

## Ao mexer no código

- **Endpoint novo que devolva dado do aluno** entra na lista do
  `backend/tests/test_isolamento.py`. A busca é sempre por `(user_id, ...)`.
- **Rota nova no frontend** depende do `SPAStaticFiles` em `main.py` — sem o
  fallback para o `index.html`, o link direto dá 404 em produção.
- **Ícone novo** entra em `frontend/src/components/Icon.tsx`, nunca como emoji.
- **Mudança de interface se mostra rodando.** Um preview temporário
  (`frontend/preview-*.html` + `src/preview-*.tsx`) monta o componente com
  dados falsos, o Playwright tira a captura, e os arquivos são apagados antes
  do commit. É como as telas foram revisadas em 18/08/2026.
- **Sem dependência nova no frontend** sem um bom motivo: o público abre isso no
  4G, e o roteador foi escrito à mão por causa disso.
- **Texto de notificação entra em `backend/tests/test_funcoes_puras.py`.** Foi
  ali que apareceu o "Hoje: 1 entrega(s)" para uma webconferência — frase de
  push quebra calada, porque ninguém a vê até chegar no celular de alguém.
- **Estado do push mora no `usePush`** (`frontend/src/lib/usePush.ts`), usado
  pelo convite e pelo perfil. Duplicado, ligar num lugar deixava o outro
  dizendo "desligado" até o reload.

## Como o Jaime trabalha

- Commite direto na `main`, sem branch e sem PR. **Push é decisão dele** —
  pergunte antes.
- Não refaça a interface inteira de uma vez. Mude uma tela, mostre rodando,
  espere a reação. Um redesign completo já foi construído e revertido.
- Ele testa em produção com a própria conta do Moodle; é o único ambiente onde
  dá para ver a agenda com dados reais. Usa iPhone — o app instalado pelo
  Safari, e a inscrição de push aponta para `web.push.apple.com`.
- Quando ele pede volume ("bastante notificação"), o objetivo é hábito. Diga o
  custo uma vez, proponha a forma que cria rotina sem queimar o canal, e siga a
  decisão dele.
