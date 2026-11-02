"""Testes da carteira contra o histórico real (itens para decisões grandes).

Todas as funções recebem a carteira (``{categoria: %}``) e a tabela de
retornos mensais de ``decisao.historico.carregar_indices``. Os resultados
são mensais: quedas dentro de um mês (como o pior dia da Covid) não
aparecem por inteiro.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from tributacao.regras import aliquota_previdencia, aliquota_rf

from .historico import retornos_carteira

# ── 1. Teste de crise ─────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Crise:
    nome: str
    inicio: str  # último mês antes da crise (valor de partida)
    fim: str  # fim da janela em que se procura o fundo


CRISES = (
    Crise("Crise financeira global (2008)", "2008-05-31", "2009-06-30"),
    Crise("Recessão e crise política (2015–2016)", "2014-08-31", "2016-02-29"),
    Crise("Covid-19 (2020)", "2020-01-31", "2020-12-31"),
    Crise("Inflação e alta dos juros (2021–2022)", "2020-12-31", "2022-12-31"),
)


def _nivel(retornos: pd.Series) -> pd.Series:
    return (1 + retornos.fillna(0)).cumprod()


def _meses_ate_recuperar(nivel: pd.Series, apos: pd.Timestamp, alvo: float) -> int | None:
    seguinte = nivel.loc[nivel.index > apos]
    recuperou = seguinte[seguinte >= alvo - 1e-12]
    if recuperou.empty:
        return None
    return int(len(nivel.loc[(nivel.index > apos) & (nivel.index <= recuperou.index[0])]))


def teste_crises(carteira: dict[str, float], valor: float, indices: pd.DataFrame) -> dict:
    """Quanto a carteira perderia em cada crise e quanto tempo levaria para voltar."""
    retornos = retornos_carteira(carteira, indices)
    nivel = _nivel(retornos)
    nivel_cdi = _nivel(indices["cdi"].reindex(nivel.index))
    crises = []
    for crise in CRISES:
        inicio, fim = pd.Timestamp(crise.inicio), pd.Timestamp(crise.fim)
        if inicio not in nivel.index or fim > nivel.index.max():
            continue
        partida = nivel.loc[inicio]
        janela = nivel.loc[inicio:fim] / partida
        fundo = janela.idxmin()
        perda = float(janela.min() - 1)
        meses_fundo = int(len(janela.loc[inicio:fundo]) - 1)
        if perda >= 0:
            recuperacao = 0
        else:
            depois = _meses_ate_recuperar(nivel, fundo, partida)
            recuperacao = None if depois is None else meses_fundo + depois
        cdi = float(nivel_cdi.loc[fim] / nivel_cdi.loc[inicio] - 1)
        carteira_fim = float(janela.loc[fim] - 1)
        crises.append(
            {
                "crise": crise.nome,
                "perda_maxima": perda,
                "perda_maxima_reais": valor * perda,
                "meses_ate_o_fundo": meses_fundo,
                "meses_para_recuperar": recuperacao,
                "carteira_no_fim": carteira_fim,
                "cdi_no_fim": cdi,
                "inicio": inicio.strftime("%m/%Y"),
                "fim": fim.strftime("%m/%Y"),
            }
        )

    # Pior queda de todo o histórico (pico a fundo), em qualquer época.
    topo = nivel.cummax()
    queda = nivel / topo - 1
    fundo = queda.idxmin()
    pico = nivel.loc[:fundo].idxmax()
    pior = float(queda.min())
    recuperar = 0 if pior >= 0 else _meses_ate_recuperar(nivel, fundo, float(nivel.loc[pico]))
    return {
        "crises": crises,
        "pior_queda": {
            "perda": pior,
            "perda_reais": valor * pior,
            "pico": pico.strftime("%m/%Y"),
            "fundo": fundo.strftime("%m/%Y"),
            "meses_ate_o_fundo": int(len(nivel.loc[pico:fundo]) - 1),
            "meses_para_recuperar": None if recuperar is None else recuperar,
        },
        "periodo": f"{nivel.index.min():%m/%Y} a {nivel.index.max():%m/%Y}",
    }


# ── 2. Faixas de resultado por prazo ──────────────────────────────────────────

PERCENTIS = (5, 10, 25, 50, 75, 90, 95)
PRAZO_MAXIMO_FAIXA = 10
_FAIXAS = {"50%": (25, 75), "80%": (10, 90), "90%": (5, 95)}
# Erro da previsão do próprio CDI (realizado − previsto pela curva Selic/Focus,
# em pontos por ano), medido na validação histórica 2013–2025: metade da
# largura de cada faixa. Prazos acima de 5 anos repetem o de 5 anos.
ERRO_CDI_PREVISTO = {
    1: {"50%": 0.006, "80%": 0.016, "90%": 0.018},
    3: {"50%": 0.026, "80%": 0.038, "90%": 0.040},
    5: {"50%": 0.023, "80%": 0.047, "90%": 0.050},
}


def _erro_cdi(anos: int, faixa: str) -> float:
    chave = 1 if anos <= 1 else 3 if anos <= 3 else 5
    return ERRO_CDI_PREVISTO[chave][faixa]


def _janelas(retornos: pd.Series, meses: int) -> pd.Series:
    fator = (1 + retornos).rolling(meses).apply(np.prod, raw=True)
    return fator.dropna()


def faixas_retorno(
    carteira: dict[str, float],
    prazo_anos: float,
    taxa_cdi_esperada: float,
    indices: pd.DataFrame,
    valor: float = 0.0,
) -> dict:
    """Faixas de 50%, 80% e 90% para o retorno anual no prazo.

    Junta duas incertezas independentes: quanto o CDI pode ficar longe do
    esperado hoje (erro medido na validação) e quanto a carteira variou em
    relação ao CDI nas janelas históricas do mesmo prazo. Os juros atuais (e
    não os do passado) servem de base.
    """
    anos = int(min(max(round(prazo_anos), 1), PRAZO_MAXIMO_FAIXA))
    meses = anos * 12
    retornos = retornos_carteira(carteira, indices)
    cdi = indices["cdi"].reindex(retornos.index).fillna(0)
    fator_carteira = _janelas(retornos, meses)
    fator_cdi = _janelas(cdi, meses).reindex(fator_carteira.index)
    excesso = (fator_carteira / fator_cdi) ** (1 / anos) - 1
    nominal = fator_carteira ** (1 / anos) - 1
    quantis = {p: float(np.percentile(excesso, p)) for p in PERCENTIS}
    mediana = (1 + taxa_cdi_esperada) * (1 + quantis[50]) - 1

    faixas = {}
    for nome, (baixo, alto) in _FAIXAS.items():
        erro = _erro_cdi(anos, nome)
        abaixo = ((quantis[50] - quantis[baixo]) ** 2 + erro**2) ** 0.5
        acima = ((quantis[alto] - quantis[50]) ** 2 + erro**2) ** 0.5
        minimo, maximo = mediana - abaixo, mediana + acima
        faixas[nome] = {
            "minimo": minimo,
            "maximo": maximo,
            "valor_minimo": valor * (1 + minimo) ** anos,
            "valor_maximo": valor * (1 + maximo) ** anos,
        }
    return {
        "anos": anos,
        "prazo_limitado": prazo_anos > PRAZO_MAXIMO_FAIXA,
        "janelas": int(len(excesso)),
        "janelas_independentes": int(len(retornos) // meses),
        "mediana": mediana,
        "valor_mediano": valor * (1 + mediana) ** anos,
        "faixas": faixas,
        "chance_perder_dinheiro": float((nominal < 0).mean()),
        "chance_abaixo_do_cdi": float((excesso < 0).mean()),
        "cdi_esperado": taxa_cdi_esperada,
    }


# ── 4. Custo de sair antes ────────────────────────────────────────────────────

HORIZONTES_SAIDA_MESES = (6, 12, 24)

_LIQUIDEZ = {
    "imediata": "No mesmo dia ou no dia seguinte",
    "tesouro": "D+1, ao preço de mercado do dia (pode ser abaixo do comprado)",
    "cdb_prazo": "Tesouro em D+1; CDB/LCI/LCA de prazo fixo podem não ter resgate antes do vencimento",
    "fundo": "Conforme a cotização do fundo (de D+0 a D+30 ou mais; veja o regulamento)",
    "bolsa": "Venda na bolsa em qualquer dia útil; dinheiro em D+2, ao preço do dia",
    "previdencia": "Após a carência do plano; trocar de plano por portabilidade não paga IR",
    "vencimento": "Em geral só no vencimento; venda antes costuma ter deságio",
}

# categoria → (grupo de IR, liquidez)
_SAIDA: dict[str, tuple[str, str]] = {
    "rf_liq": ("rf", "imediata"), "rf_reserva": ("rf", "imediata"),
    "rf_selic_cdb": ("rf", "imediata"), "rf_reavalie": ("rf", "imediata"),
    "rf": ("rf", "cdb_prazo"), "rf_ipca": ("rf", "tesouro"), "rf_equilibrio": ("rf", "tesouro"),
    "fundos_rf": ("fundo_rf", "fundo"), "fundos_rf_liq": ("fundo_rf", "fundo"),
    "fundos": ("fundo_rf", "fundo"), "fundos_div": ("fundo_rf", "fundo"),
    "fundos_multi": ("fundo_rf", "fundo"),
    "fundos_acoes": ("acoes", "fundo"), "fundos_dca": ("acoes", "fundo"),
    "fundos_etf": ("acoes", "bolsa"), "rv": ("acoes", "bolsa"), "rv_dca": ("acoes", "bolsa"),
    "rv_compl": ("acoes", "bolsa"), "cambio": ("acoes", "bolsa"),
    "fiis": ("fii", "bolsa"), "fiis_del": ("fii", "bolsa"),
    "rv_cripto": ("cripto", "bolsa"), "fundos_cripto": ("acoes", "bolsa"),
    "prev_vgbl": ("vgbl", "previdencia"), "prev_vgbl_rf": ("vgbl", "previdencia"),
    "prev_pgbl": ("pgbl", "previdencia"), "prev_pgbl_rf": ("pgbl", "previdencia"),
    "coe": ("rf", "vencimento"), "estruturados": ("rf", "vencimento"),
    "ofertas": ("acoes", "vencimento"),
}


def _imposto_saida(grupo: str, valor: float, ganho: float, meses: int) -> float:
    """IR estimado no resgate (regime regressivo na previdência)."""
    dias = int(meses * 30.4)
    ganho_positivo = max(ganho, 0.0)
    if grupo == "rf":
        return ganho_positivo * aliquota_rf(dias)
    if grupo == "fundo_rf":
        # Come-cotas antecipa parte do IR; no total, a alíquota final é a regressiva.
        return ganho_positivo * aliquota_rf(dias)
    if grupo == "acoes":
        return ganho_positivo * 0.15
    if grupo == "fii":
        return ganho_positivo * 0.20
    if grupo == "cripto":
        return ganho_positivo * 0.15
    if grupo == "vgbl":
        return ganho_positivo * aliquota_previdencia(meses / 12)
    if grupo == "pgbl":
        # No PGBL o IR incide sobre todo o valor resgatado, não só o ganho.
        return (valor + ganho) * aliquota_previdencia(meses / 12)
    return 0.0


def custo_de_sair(
    carteira: dict[str, float],
    valor: float,
    taxa_esperada: float,
    indices: pd.DataFrame,
    horizontes: tuple[int, ...] = HORIZONTES_SAIDA_MESES,
) -> list[dict]:
    """Por classe: quanto sobra se resgatar em 6, 12 ou 24 meses.

    "Central" usa a taxa esperada da carteira; "pior caso" aplica a ela a
    diferença em relação ao CDI das 5% piores janelas históricas da classe
    com o mesmo prazo (assim os juros de hoje, e não os do passado, são a base).
    """
    soma = sum(float(p) for p in carteira.values()) or 1.0
    linhas = []
    for categoria, peso in carteira.items():
        if float(peso) <= 0:
            continue
        aplicado = valor * float(peso) / soma
        grupo, liquidez = _SAIDA.get(categoria, ("rf", "fundo"))
        retornos = retornos_carteira({categoria: 100}, indices)
        cdi = indices["cdi"].reindex(retornos.index).fillna(0)
        linha = {
            "categoria": categoria,
            "percentual": float(peso) / soma * 100,
            "valor": aplicado,
            "liquidez": _LIQUIDEZ[liquidez],
            "horizontes": [],
        }
        for meses in horizontes:
            ganho_central = aplicado * ((1 + taxa_esperada) ** (meses / 12) - 1)
            # Pior caso: a taxa esperada hoje, piorada pela diferença em relação
            # ao CDI das 5% piores janelas históricas da classe no mesmo prazo.
            janelas = _janelas(retornos, meses)
            relativo = janelas / _janelas(cdi, meses).reindex(janelas.index)
            fator_central = (1 + taxa_esperada) ** (meses / 12)
            pior = (
                float(fator_central * np.percentile(relativo, 5) - 1)
                if len(relativo)
                else fator_central - 1
            )
            ganho_pior = aplicado * pior
            ir_central = _imposto_saida(grupo, aplicado, ganho_central, meses)
            ir_pior = _imposto_saida(grupo, aplicado, ganho_pior, meses)
            linha["horizontes"].append(
                {
                    "meses": meses,
                    "liquido_central": aplicado + ganho_central - ir_central,
                    "ir_central": ir_central,
                    "liquido_pior_caso": aplicado + ganho_pior - ir_pior,
                    "retorno_pior_caso": pior,
                }
            )
        linhas.append(linha)
    return linhas


# ── 5. Investir tudo de uma vez ou parcelar a entrada ─────────────────────────


def _simular_entrada(rc: np.ndarray, rcdi: np.ndarray, parcelas: int) -> float:
    """Valor final (para 1 real) entrando em ``parcelas`` meses; o resto fica no CDI."""
    investido, caixa = 0.0, 1.0
    for mes in range(len(rc)):
        if mes < parcelas:
            aporte = 1.0 / parcelas
            caixa -= aporte
            investido += aporte
        investido *= 1 + rc[mes]
        caixa *= 1 + rcdi[mes]
    return investido + max(caixa, 0.0)


def entrada_parcelada(
    carteira: dict[str, float],
    valor: float,
    indices: pd.DataFrame,
    parcelas: tuple[int, ...] = (6, 12),
    horizonte_meses: int = 24,
) -> dict:
    """Compara, em todas as datas do histórico, entrar de uma vez x parcelar.

    Enquanto não entra na carteira, o dinheiro fica rendendo CDI. Todos são
    medidos no mesmo horizonte (24 meses por padrão).
    """
    retornos = retornos_carteira(carteira, indices)
    cdi = indices["cdi"].reindex(retornos.index).fillna(0).to_numpy()
    rc = retornos.to_numpy()
    inicios = range(0, len(rc) - horizonte_meses + 1)
    resultados: dict[int, list[float]] = {1: [], **{p: [] for p in parcelas}}
    for i in inicios:
        fatia_c, fatia_cdi = rc[i : i + horizonte_meses], cdi[i : i + horizonte_meses]
        for p in resultados:
            resultados[p].append(_simular_entrada(fatia_c, fatia_cdi, p))
    estrategias = []
    de_uma_vez = np.array(resultados[1])
    for p, valores in resultados.items():
        arr = np.array(valores)
        estrategias.append(
            {
                "parcelas": p,
                "nome": "Tudo de uma vez" if p == 1 else f"Em {p} parcelas mensais",
                "mediana": valor * float(np.median(arr)),
                "pior_caso": valor * float(arr.min()),
                "pior_5pct": valor * float(np.percentile(arr, 5)),
                "melhor_caso": valor * float(arr.max()),
                "venceu_de_uma_vez": None if p == 1 else float((arr > de_uma_vez).mean()),
            }
        )
    return {
        "horizonte_meses": horizonte_meses,
        "datas_testadas": len(de_uma_vez),
        "estrategias": estrategias,
        "faz_diferenca": bool(
            max(e["pior_caso"] for e in estrategias) - min(e["pior_caso"] for e in estrategias)
            > 0.01 * valor
        ),
    }


def meses_por_extenso(meses: int | None) -> str:
    if meses is None:
        return "ainda não recuperou"
    if meses == 0:
        return "não caiu"
    anos, resto = divmod(meses, 12)
    partes = []
    if anos:
        partes.append(f"{anos} ano" + ("s" if anos > 1 else ""))
    if resto:
        partes.append(f"{resto} {'mês' if resto == 1 else 'meses'}")
    return " e ".join(partes)


__all__ = [
    "CRISES",
    "custo_de_sair",
    "entrada_parcelada",
    "faixas_retorno",
    "meses_por_extenso",
    "teste_crises",
]

