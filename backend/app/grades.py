"""
A conta que o aluno faz no papel: quanto ainda precisa tirar para passar.

O Moodle mostra as notas lançadas e nada mais. Quem quer saber se ainda dá para
fechar a média soma peso por peso na calculadora do celular, no meio do
semestre, geralmente errado — e é a pergunta que decide se ele vai estudar
neste fim de semana ou no seguinte.

## O que impede a conta

O Moodle da UNOESC só atribui peso ao item **depois** de lançar a nota dele.
Durante boa parte do semestre a soma dos pesos conhecidos é bem menor que 100%,
e aí `(passing - parcial) / peso_pendente` produz um número que parece
resposta e não é: o denominador não cobre o que ainda vem. Por isso
`SOMA_MINIMA` — abaixo dela a função devolve `sem_base` e a tela diz que ainda
não dá para calcular, em vez de inventar um "precisa de 4,1" que faz alguém
relaxar antes da prova que decide.

Este módulo é puro de propósito: nada aqui fala com o Moodle nem com o banco,
e por isso `tests/test_funcoes_puras.py` consegue cobrir os casos que mais
importam — o que já está garantido, o que já não fecha, e o que não dá para
saber.
"""

from typing import Optional, TypedDict

# Quanto os pesos precisam somar para a conta significar alguma coisa. Não é
# 100 exato: escala do Moodle arredonda ("33,33%" três vezes dá 99,99), e
# professor que reparte 100% em sete avaliações raramente fecha na vírgula.
SOMA_MINIMA = 95.0
SOMA_MAXIMA = 105.0


class Previsao(TypedDict):
    """O que dá para dizer hoje sobre a média final desta disciplina."""

    # Média parcial na escala 0–10, contando só o que já tem nota e peso.
    atual: Optional[float]
    # Quantas avaliações ainda não têm nota lançada.
    pendentes: int
    # Nota necessária, em média, no que falta. `None` quando não se aplica.
    precisa: Optional[float]
    # fechado | garantido | precisa | impossivel | sem_base
    situacao: str


def _soma_pesos(itens: list[dict]) -> float:
    return sum(i.get("peso") or 0 for i in itens)


def prever(itens: list[dict], corte: float = 7.0) -> Previsao:
    """
    A previsão da disciplina a partir do boletim item a item.

    Cada item é `{"nome", "peso" (% do total), "nota", "maximo"}` — o formato
    que `MoodleClient.course_grade_items` devolve e que a tabela `grade_items`
    guarda. Item sem nota conta como pendente, nunca como zero: tratar vazio
    como zero diria "você está reprovado" para quem ainda não fez a prova.
    """
    if not itens:
        return {"atual": None, "pendentes": 0, "precisa": None, "situacao": "sem_base"}

    parcial = 0.0
    peso_pendente = 0.0
    pendentes = 0
    lancadas = 0

    for item in itens:
        peso = item.get("peso") or 0
        nota = item.get("nota")
        maximo = item.get("maximo") or 10
        if nota is None:
            pendentes += 1
            peso_pendente += peso
            continue
        if maximo:
            parcial += (peso / 100) * (nota / maximo) * 10
            lancadas += 1

    # Nenhuma nota lançada não é média zero: é média que ainda não existe.
    # Mostrar "0,0" para quem não fez nenhuma prova é dizer que ele já está
    # reprovado.
    atual = round(parcial, 2) if lancadas else None
    soma = _soma_pesos(itens)

    # Sem os pesos fechando, o denominador não representa o que falta.
    if not (SOMA_MINIMA <= soma <= SOMA_MAXIMA):
        return {
            "atual": atual,
            "pendentes": pendentes,
            "precisa": None,
            "situacao": "sem_base",
        }

    if peso_pendente <= 0:
        return {"atual": atual, "pendentes": 0, "precisa": None, "situacao": "fechado"}

    precisa = round((corte - parcial) / (peso_pendente / 100), 2)

    if precisa <= 0:
        # Fecha a média mesmo zerando tudo o que falta.
        return {"atual": atual, "pendentes": pendentes, "precisa": 0.0,
                "situacao": "garantido"}
    if precisa > 10:
        # Nem tirando o máximo no que resta. Dizer isso é duro, mas descobrir
        # sozinho na semana da prova final é pior.
        return {"atual": atual, "pendentes": pendentes, "precisa": precisa,
                "situacao": "impossivel"}

    return {"atual": atual, "pendentes": pendentes, "precisa": precisa,
            "situacao": "precisa"}


def frase(previsao: Previsao, corte: float = 7.0) -> Optional[str]:
    """
    A previsão em uma linha, para o cartão da disciplina. `None` quando não há
    o que dizer — cartão com "não foi possível calcular" é ruído.

    O texto sai do backend porque a mesma frase serve à lista e, um dia, à
    notificação: duas redações do mesmo cálculo divergem no primeiro ajuste.
    """
    def n(v: float) -> str:
        return f"{v:.1f}".replace(".", ",")

    situacao = previsao["situacao"]
    atual = previsao["atual"]

    if situacao == "garantido" and atual is not None:
        return f"Aprovação garantida — fecha em {n(atual)} mesmo zerando o que falta."
    if situacao == "precisa" and previsao["precisa"] is not None:
        quantas = previsao["pendentes"]
        onde = "na avaliação que falta" if quantas == 1 else f"em cada uma das {quantas} que faltam"
        return f"Precisa de {n(previsao['precisa'])} {onde} para fechar {n(corte)}."
    if situacao == "impossivel":
        return f"Não fecha {n(corte)} com o que falta — procure o professor."
    if situacao == "fechado" and atual is not None:
        return (f"Fechou em {n(atual)}." if atual >= corte
                else f"Fechou em {n(atual)}, abaixo de {n(corte)}.")
    return None
