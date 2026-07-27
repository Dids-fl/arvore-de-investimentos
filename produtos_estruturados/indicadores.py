# produtos_estruturados/indicadores.py
"""
Cruza cadastro (CRA/CRI/Debênture) com negociação em balcão agregada e
calcula os indicadores usados no ranking: prazo até o vencimento, liquidez
(proxy via nº de negócios/volume), isenção de IR e taxa de referência.

IMPORTANTE (validado em produção, jul/2026):
- `B3.securitizadoras()` está confirmadamente com o endpoint desatualizado
  (retorna 0 registros) — então `cadastro['cras']`/`cadastro['cris']`
  costumam vir vazios. Como paliativo, quando isso acontece este módulo
  reconstrói um cadastro mínimo de CRA/CRI a partir da própria negociação
  balcão (que já traz `instrumento`, `codigo_isin` e `emissor` para CRA/CRI
  negociados recentemente). Não é um cadastro completo — só cobre ativos
  que negociaram na janela consultada — mas é melhor que zero.
- Os nomes de coluna do CSV de `debentures()` variam conforme a B3 muda o
  layout do arquivo. Em vez de chaves fixas, usamos busca tolerante
  (case-insensitive, por substring) — ver `_buscar_campo()`.
"""

import logging
import re
from datetime import date, datetime

from renda_fixa.coletor import coletar_indicadores

logger = logging.getLogger(__name__)

# Limiar da heurística de normalização de taxa (ver _normalizar_taxa).
# Nenhum CRA/CRI/Debênture real paga uma taxa FIXA acima de ~25-30% a.a.
# no Brasil — valores acima disso, negociados em balcão, são quase
# sempre "% do CDI" (ex.: 89,99 = 89,99% do CDI), não uma taxa direta.
LIMIAR_PROVAVEL_PERCENTUAL_CDI = 30.0


def _normalizar_taxa(taxa_bruta, cdi_atual: float | None):
    """
    A B3 (via `negociacao_balcao`) não classifica o indexador do negócio
    (%CDI vs prefixado vs IPCA+ spread) — só devolve um número cru em
    "Taxa Negocio". Isso é uma limitação real de dados: sem o indexador
    explícito, não há como saber com 100% de certeza o que o número
    representa. A heurística abaixo, validada contra dados reais de
    produção (jul/2026 — valores como 89.99, 95.09, 109.50, 112.00 nos
    negócios de CRA), assume:

      taxa_bruta > 30           -> provavelmente "% do CDI"
                                     equivalente a.a. = (taxa/100) * CDI
      taxa_bruta <= 30          -> tratada como taxa direta (prefixado
                                     ou IPCA+spread já expresso em % a.a.)

    Retorna (taxa_equivalente_aa, indexador_estimado).
    """
    if taxa_bruta is None:
        return None, None

    if taxa_bruta > LIMIAR_PROVAVEL_PERCENTUAL_CDI and cdi_atual:
        equivalente = round(taxa_bruta / 100 * cdi_atual * 100, 2)
        return equivalente, "%CDI (estimado)"

    return round(float(taxa_bruta), 2), "direto/IPCA+ (estimado)"


_CDI_CACHE: dict[str, float] = {}


def _obter_cdi_atual() -> float | None:
    if "cdi" in _CDI_CACHE:
        return _CDI_CACHE["cdi"]
    try:
        _, cdi = coletar_indicadores()
        _CDI_CACHE["cdi"] = cdi
        return cdi
    except Exception as e:
        logger.warning(f"Não foi possível obter o CDI para normalizar taxas: {e}")
        return None

# Debêntures "incentivadas" (Lei 12.431) são isentas de IR para pessoa
# física; CRA e CRI já são isentos por natureza.
CAMPOS_INCENTIVADA = ("incentivada", "lei 12.431", "12431", "12.431")

# Candidatos de nome de coluna (substring, case-insensitive) para os
# campos que precisamos extrair de registros de debênture/CRA/CRI, já que
# o layout exato do CSV da B3 muda com o tempo.
_CANDIDATOS_VENCIMENTO = ("vencimento",)
_CANDIDATOS_ISIN = ("isin",)
_CANDIDATOS_EMISSOR = ("emissor", "razao social", "razaosocial", "companhia")
_CANDIDATOS_IDENTIFICADOR = ("nome", "codigo", "ativo", "denomina")


def _buscar_campo(registro: dict, candidatos: tuple[str, ...]):
    """Procura, entre as chaves do registro, a primeira cujo nome (em
    minúsculas) contenha algum dos termos de `candidatos`. Retorna o valor
    ou None."""
    for chave, valor in registro.items():
        chave_norm = str(chave).lower()
        if any(termo in chave_norm for termo in candidatos):
            if valor not in (None, ""):
                return valor
    return None


def _parse_data(valor):
    if not valor:
        return None
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    # Tenta extrair um padrão dd/mm/aaaa ou aaaa-mm-dd de dentro de um texto maior
    m = re.search(r"(\d{2}/\d{2}/\d{4})|(\d{4}-\d{2}-\d{2})", texto)
    if m:
        return _parse_data(m.group(0))
    return None


def _prazo_dias(vencimento):
    venc = _parse_data(vencimento)
    if venc is None:
        return None
    return max((venc - date.today()).days, 0)


def _isento_ir(tipo: str, registro: dict) -> bool:
    if tipo in ("CRA", "CRI"):
        return True
    if tipo == "DEBENTURE":
        # Padrão 1 (confirmado real na B3): coluna dedicada, ex.
        # 'Destinação do recurso (Lei 12.431)' com valor 'Sim'/'Não'.
        # Buscamos pela CHAVE e interpretamos o VALOR daquela coluna.
        for chave, valor in registro.items():
            chave_norm = str(chave).lower().replace(".", "")
            if any(termo.replace(".", "") in chave_norm for termo in CAMPOS_INCENTIVADA):
                valor_norm = str(valor).strip().lower()
                return valor_norm in ("sim", "true", "1", "yes")

        # Padrão 2 (fallback): fontes que descrevem a isenção dentro do
        # próprio valor de outro campo (ex. "Espécie": "Incentivada Lei 12.431").
        texto = " ".join(str(v).lower() for v in registro.values())
        texto_norm = texto.replace(".", "")
        return any(termo.replace(".", "") in texto_norm for termo in CAMPOS_INCENTIVADA)
    return False


def _score_liquidez(n_negocios: int, volume_total: float) -> float:
    """Score de 0 a 10 combinando frequência de negócios e volume
    financeiro acumulado na janela coletada. Ativos de balcão são
    naturalmente pouco líquidos, então a escala é conservadora."""
    if not n_negocios:
        return 0.0
    score_freq = min(n_negocios / 10, 1.0) * 5      # até 10 negócios = 5 pts
    score_vol = min(volume_total / 5_000_000, 1.0) * 5  # até R$5mi = 5 pts
    return round(score_freq + score_vol, 2)


def _fallback_cra_cri_via_negociacao(negociacao_agregada: dict) -> list[dict]:
    """
    Usado quando `cadastro['cras']`/`cadastro['cris']` vêm vazios (endpoint
    `securitizadoras()` desatualizado — caso confirmado em produção).
    Reconstrói um cadastro mínimo de CRA/CRI a partir dos próprios negócios
    de balcão coletados, que já trazem instrumento, ISIN e emissor.

    Limitação conhecida: só cobre ativos que negociaram na janela
    consultada (ex.: últimos 20 dias) — não é o cadastro completo, mas
    evita ficar com 0 CRA/CRI quando eles claramente existem e negociam
    (como visto no log real: BRIMWLCRA1A7, BRRBRACIR2E1 etc.).
    """
    fallback = []
    for isin, dados in negociacao_agregada.items():
        instrumento = (dados.get("instrumento") or "").upper()
        if instrumento not in ("CRA", "CRI"):
            continue
        fallback.append({
            "isin": isin,
            "_tipo": instrumento,
            "emissor": dados.get("emissor"),
            # Sem cadastro oficial não temos data de vencimento — fica None
            # e o filtro por prazo trata isso corretamente (ver filtros.py).
            "_origem": "negociacao_balcao (fallback, sem cadastro oficial)",
        })
    return fallback


def montar_indicadores(cadastro: dict, negociacao_agregada: dict) -> list[dict]:
    """
    Retorna uma lista de dicts, um por ativo (CRA, CRI ou Debênture), com:
        tipo, identificador, emissor, isin, taxa, prazo_dias, isento_ir,
        score_liquidez, tem_negociacao_recente
    Ativos sem ISIN localizável na negociação recente entram com
    score_liquidez=0 e tem_negociacao_recente=False (ainda participam do
    ranking, mas perdem pontos de liquidez — ver produtos_estruturados/filtros.py).
    """
    ativos = []
    cdi_atual = _obter_cdi_atual()

    cras = cadastro.get("cras", [])
    cris = cadastro.get("cris", [])

    if not cras and not cris:
        logger.warning(
            "Cadastro de CRA/CRI veio vazio (securitizadoras() desatualizado?). "
            "Usando fallback via negociação balcão — cobertura parcial."
        )
        fallback = _fallback_cra_cri_via_negociacao(negociacao_agregada)
        cras = [f for f in fallback if f["_tipo"] == "CRA"]
        cris = [f for f in fallback if f["_tipo"] == "CRI"]

    for tipo, registros in (("CRA", cras), ("CRI", cris)):
        for reg in registros:
            isin = _buscar_campo(reg, _CANDIDATOS_ISIN) or reg.get("isin")
            neg = negociacao_agregada.get(isin, {}) if isin else {}
            vencimento = _buscar_campo(reg, _CANDIDATOS_VENCIMENTO)
            nome_base = (
                _buscar_campo(reg, _CANDIDATOS_IDENTIFICADOR)
                or _buscar_campo(reg, _CANDIDATOS_EMISSOR)
                or isin
            )
            taxa_bruta = neg.get("taxa_ultima")
            taxa, indexador_estimado = _normalizar_taxa(taxa_bruta, cdi_atual)
            ativos.append({
                "tipo": tipo,
                # Inclui o ISIN no identificador: com o fallback, vários
                # ativos do mesmo emissor (mesma securitizadora) ficam sem
                # nome individual — só o ISIN distingue um do outro.
                "identificador": f"{nome_base} — {isin}" if isin and isin not in str(nome_base) else nome_base,
                "emissor": _buscar_campo(reg, _CANDIDATOS_EMISSOR) or reg.get("_securitizadora_cnpj"),
                "isin": isin,
                "vencimento": vencimento,
                "prazo_dias": _prazo_dias(vencimento),
                "isento_ir": _isento_ir(tipo, reg),
                "taxa": taxa,
                "taxa_bruta": taxa_bruta,
                "indexador_estimado": indexador_estimado,
                "score_liquidez": _score_liquidez(neg.get("n_negocios", 0), neg.get("volume_total", 0.0)),
                "tem_negociacao_recente": isin in negociacao_agregada,
                "fonte": reg.get("_origem", "mercados/B3"),
                # True quando o registro veio do fallback de negociação
                # balcão (sem cadastro oficial de CRA/CRI — endpoint
                # securitizadoras() desatualizado). Nesses casos não temos
                # como saber a data de vencimento real.
                "sem_cadastro_oficial": "_origem" in reg,
            })

    for reg in cadastro.get("debentures", []):
        isin = _buscar_campo(reg, _CANDIDATOS_ISIN)
        neg = negociacao_agregada.get(isin, {}) if isin else {}
        vencimento = _buscar_campo(reg, _CANDIDATOS_VENCIMENTO)
        taxa_bruta = neg.get("taxa_ultima")
        taxa, indexador_estimado = _normalizar_taxa(taxa_bruta, cdi_atual)
        ativos.append({
            "tipo": "DEBENTURE",
            "identificador": (
                _buscar_campo(reg, _CANDIDATOS_IDENTIFICADOR)
                or _buscar_campo(reg, _CANDIDATOS_EMISSOR)
                or isin
            ),
            "emissor": _buscar_campo(reg, _CANDIDATOS_EMISSOR),
            "isin": isin,
            "vencimento": vencimento,
            "prazo_dias": _prazo_dias(vencimento),
            "isento_ir": _isento_ir("DEBENTURE", reg),
            "taxa": taxa,
            "taxa_bruta": taxa_bruta,
            "indexador_estimado": indexador_estimado,
            "score_liquidez": _score_liquidez(neg.get("n_negocios", 0), neg.get("volume_total", 0.0)),
            "tem_negociacao_recente": isin in negociacao_agregada,
            "fonte": "mercados/B3",
            "sem_cadastro_oficial": False,
        })

    sem_vencimento = sum(1 for a in ativos if a["prazo_dias"] is None)
    logger.info(
        f"Indicadores montados para {len(ativos)} ativos de produtos estruturados "
        f"({sem_vencimento} sem data de vencimento localizável — ficam de fora do ranking)."
    )
    return ativos