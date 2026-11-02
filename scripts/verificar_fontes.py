"""Verifica se cada fonte de dados gratuita ainda responde no formato esperado.

Fontes gratuitas mudam de layout sem aviso (foi assim que a tabela de FIIs
do Fundamentus deixou de ser lida). Este script faz uma consulta pequena a
cada fonte, usando o próprio código do app, e confere se o resultado tem a
forma esperada. Não baixa os vários GB da CVM: só confere que os arquivos
existem.

Uso:
    python scripts/verificar_fontes.py            # tabela no terminal
    python scripts/verificar_fontes.py --markdown resumo.md

Sai com código 1 se alguma fonte essencial falhar. Fontes marcadas como
"bloqueio de nuvem" (Status Invest, sistemas da B3) costumam recusar
servidores em nuvem, inclusive o GitHub Actions, e não reprovam a execução.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ESSENCIAL = "essencial"
OPCIONAL = "opcional"
NUVEM = "bloqueio de nuvem"


def _bcb_sgs() -> str:
    import mercado

    selic, ref = mercado._fetch_sgs_value(mercado.SGS_SELIC)
    cdi, _ = mercado._fetch_sgs_value(mercado.SGS_CDI_ANUAL)
    assert 0 < selic < 1 and 0 < cdi < 1
    return f"Selic {selic:.2%} (ref. {ref}), CDI {cdi:.2%}"


def _focus() -> str:
    import mercado

    selic = mercado._fetch_focus_selic_por_ano()
    ipca = mercado._fetch_focus_ipca_por_ano()
    assert selic and ipca, "Focus sem medianas"
    return f"{len(selic)} anos de Selic, {len(ipca)} de IPCA"


def _yahoo() -> str:
    import mercado

    vol = mercado._fetch_ibov_volatilidade_10a()
    assert vol is not None and 0.05 < vol < 1, f"volatilidade inesperada: {vol}"
    return f"volatilidade do Ibovespa {vol:.1%}"


def _tesouro() -> str:
    from renda_fixa.coletor import coletar_tesouro

    titulos = coletar_tesouro()
    assert titulos and len(titulos) >= 10, "poucos títulos"
    tipos = {t["tipo"] for t in titulos}
    assert {"SELIC", "IPCA", "Prefixado"} <= tipos, f"tipos: {tipos}"
    return f"{len(titulos)} títulos à venda"


def _cvm() -> str:
    import requests

    from fundos import cvm_informe_diario_downloader as informe

    hoje = date.today()
    mes = hoje.month - 1 or 12
    ano = hoje.year if hoje.month > 1 else hoje.year - 1
    url = informe._url_zip(ano, mes)
    resposta = requests.head(url, timeout=30, allow_redirects=True)
    assert resposta.status_code == 200, f"{url}: HTTP {resposta.status_code}"
    cadastro = requests.head(
        "https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip",
        timeout=30,
        allow_redirects=True,
    )
    assert cadastro.status_code == 200, f"cadastro: HTTP {cadastro.status_code}"
    return f"informe {ano}-{mes:02d} e cadastro disponíveis"


def _fundamentus_acoes() -> str:
    from acoes_fiis.apis.fundamentus_scraper import get_all_bulk

    get_all_bulk.limpar_cache()
    acoes = get_all_bulk()
    assert len(acoes) > 300, f"só {len(acoes)} ações"
    assert any(a.get("pl") for a in acoes.values()), "colunas sem P/L"
    return f"{len(acoes)} ações"


def _fundamentus_fiis() -> str:
    from acoes_fiis.apis.fundamentus_scraper import get_fiis_bulk

    get_fiis_bulk.limpar_cache()
    fiis = get_fiis_bulk()
    assert len(fiis) > 100, f"só {len(fiis)} FIIs"
    assert any(f.get("dy") for f in fiis.values()), "colunas sem dividend yield"
    return f"{len(fiis)} FIIs"


def _brapi() -> str:
    from acoes_fiis.apis import brapi_tickers

    brapi_tickers._cache.update(ts=0.0, dados=None)
    ativos = brapi_tickers.listar_tickers()
    etfs = sum(str(a.get("subType", "")).lower() == "etf" for a in ativos.values())
    assert len(ativos) > 1000 and etfs > 50, f"{len(ativos)} ativos, {etfs} ETFs"
    return f"{len(ativos)} ativos, {etfs} ETFs"


def _coingecko() -> str:
    from cripto.apis.coingecko import CoinGeckoClient

    mercados = CoinGeckoClient()._get(
        "coins/markets",
        params={"vs_currency": "brl", "order": "market_cap_desc", "per_page": 10, "page": 1},
    )
    assert mercados and "current_price" in mercados[0], "formato inesperado"
    return f"{len(mercados)} moedas, 1ª: {mercados[0]['symbol'].upper()}"


def _status_invest() -> str:
    import requests

    resposta = requests.get(
        "https://statusinvest.com.br/category/advancedsearchresultpaginated",
        params={"search": "{}", "categoryType": 1, "take": 1},
        headers={"User-Agent": "Mozilla/5.0"},
        timeout=20,
    )
    resposta.raise_for_status()
    return "respondeu"


def _b3_balcao() -> str:
    import requests

    resposta = requests.get(
        "https://sistemaswebb3-balcao.b3.com.br/featuresDebenturesProxy/DebenturesCall/GetDownload",
        timeout=20,
    )
    resposta.raise_for_status()
    return "respondeu"


VERIFICACOES: list[tuple[str, str, Callable[[], str]]] = [
    ("Banco Central (SGS)", ESSENCIAL, _bcb_sgs),
    ("Banco Central (Focus)", OPCIONAL, _focus),
    ("Yahoo Finance (Ibovespa)", OPCIONAL, _yahoo),
    ("Tesouro Transparente", ESSENCIAL, _tesouro),
    ("CVM (fundos)", ESSENCIAL, _cvm),
    ("Fundamentus (ações)", ESSENCIAL, _fundamentus_acoes),
    ("Fundamentus (FIIs)", ESSENCIAL, _fundamentus_fiis),
    ("BRAPI (lista de ativos)", ESSENCIAL, _brapi),
    ("CoinGecko", OPCIONAL, _coingecko),
    ("Status Invest", NUVEM, _status_invest),
    ("B3 balcão (CRA/CRI/debêntures)", NUVEM, _b3_balcao),
]


def executar() -> list[dict]:
    resultados = []
    for nome, tipo, verificar in VERIFICACOES:
        inicio = time.time()
        try:
            detalhe = verificar()
            ok = True
        except Exception as exc:  # noqa: BLE001 — registrar qualquer falha
            detalhe = f"{type(exc).__name__}: {str(exc)[:160]}"
            ok = False
        resultados.append(
            {
                "fonte": nome,
                "tipo": tipo,
                "ok": ok,
                "detalhe": detalhe,
                "segundos": round(time.time() - inicio, 1),
            }
        )
        icone = "✅" if ok else ("⚠️ " if tipo == NUVEM else "❌")
        print(f"{icone} {nome:34} {detalhe}", flush=True)
    return resultados


def markdown(resultados: list[dict]) -> str:
    linhas = [
        "## Verificação das fontes de dados",
        "",
        "| Fonte | Tipo | Situação | Detalhe |",
        "|---|---|---|---|",
    ]
    for r in resultados:
        situacao = "✅ ok" if r["ok"] else ("⚠️ bloqueada" if r["tipo"] == NUVEM else "❌ falhou")
        linhas.append(f"| {r['fonte']} | {r['tipo']} | {situacao} | {r['detalhe']} |")
    return "\n".join(linhas) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--markdown", help="Arquivo onde gravar o resumo em Markdown.")
    args = parser.parse_args()
    resultados = executar()
    if args.markdown:
        Path(args.markdown).write_text(markdown(resultados), encoding="utf-8")
    falhas = [r for r in resultados if not r["ok"] and r["tipo"] == ESSENCIAL]
    if falhas:
        print(f"\n{len(falhas)} fonte(s) essencial(is) falharam.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
