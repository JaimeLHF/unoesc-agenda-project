# Tirar a senha do Moodle do fluxo

O app guarda a senha do Moodle cifrada no servidor. O motivo está em
`backend/app/crypto.py` e é real: o cliente precisa relogar sozinho quando a
sessão do Moodle expira no meio do uso. Mas guardar credencial de terceiro é o
teto do projeto — é o que impede convidar uma turma inteira com sossego.

A saída não é criptográfica, é institucional: o Moodle emite um **token de web
service por aluno**, e a senha sai do fluxo inteiro.

Esta página tem duas partes: o pedido pronto para mandar à TI da UNOESC e o
que muda no código quando a resposta vier.

## O que pedir à UNOESC

> Assunto: habilitação de web service no Moodle para uso pelo próprio aluno
>
> Sou aluno do curso de Análise e Desenvolvimento de Sistemas (Unoesc Virtual)
> e mantenho um projeto pessoal que reúne, numa única agenda, os prazos e as
> webconferências que já aparecem no Moodle do aluno.
>
> Hoje o aplicativo precisa da senha do aluno para navegar no Moodle em nome
> dele. Gostaria de eliminar isso. Para tanto, peço a habilitação do serviço
> web móvel do Moodle (`moodle_mobile_app`) ou de um serviço externo dedicado,
> de modo que cada aluno gere o próprio token e informe apenas o token ao
> aplicativo.
>
> As funções necessárias são somente de leitura da própria conta:
>
> - `core_webservice_get_site_info`
> - `core_enrol_get_users_courses`
> - `core_calendar_get_action_events_by_timesort`
> - `core_course_get_contents`
> - `gradereport_user_get_grade_items`
>
> O token é emitido pelo próprio aluno, vale só para os dados dele e pode ser
> revogado por ele ou pela instituição a qualquer momento. Nenhuma senha
> passaria a ser armazenada.

Vale anexar o endereço do app e deixar claro que ele não é serviço oficial da
UNOESC.

## O que muda no código

O `MoodleClient` já isola o transporte: todas as consultas passam por
`_ajax()`, que fala com `/lib/ajax/service.php` usando o cookie de sessão. Com
token, a mesma chamada vira `GET /webservice/rest/server.php` com
`wstoken`, `wsfunction` e `moodlewsrestformat=json`.

Na prática:

1. `MoodleClient.login()` ganha um caminho alternativo: recebido um token, ele
   pula o login por formulário e guarda o token.
2. `_ajax()` passa a ter um irmão `_ws()`, e cada consulta escolhe conforme o
   que a sessão tem. As funções do web service devolvem o mesmo conteúdo com
   nomes de campo ligeiramente diferentes — o mapeamento fica no mesmo lugar
   onde hoje se lê a resposta do AJAX.
3. `crypto.py` deixa de ser necessário para senha e passa a cifrar o token (ou
   some, se o token puder ficar em claro — ele é revogável e restrito a
   leitura, ao contrário da senha).
4. A tela de login troca "senha" por "token", com um link explicando onde o
   aluno gera o dele no Moodle.

Enquanto a UNOESC não responder, nada disso pode ser construído às cegas: as
funções acima podem estar desabilitadas na instância, exatamente como estão
hoje no AJAX (`servicenotavailable` para as de nota — foi por isso que o
boletim do app lê HTML).

## Como saber se já dá para tentar

`scripts/probes/probe_notas.py` mostra o padrão: entrar com uma conta real e
imprimir o que o servidor devolve. Um probe equivalente para web service é uma
requisição só:

```bash
curl "https://ead.unoesc.edu.br/webservice/rest/server.php?wstoken=SEU_TOKEN&wsfunction=core_webservice_get_site_info&moodlewsrestformat=json"
```

Se isso responder com os dados do site em vez de um erro de serviço
desabilitado, o caminho está aberto.
