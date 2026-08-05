"""Sincronização automática e validada do calendário oficial da B3."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import unicodedata
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup, Tag

from calendarios.validacao import (
    CalendarioExtraido,
    fonte_b3_oficial,
    validar_calendario_extraido,
)

URL_CALENDARIO_B3 = (
    "https://www.b3.com.br/pt_br/solucoes/plataformas/"
    "puma-trading-system/para-participantes-e-traders/"
    "calendario-de-negociacao/feriados/"
)
MESES = {
    "janeiro": 1,
    "fevereiro": 2,
    "marco": 3,
    "abril": 4,
    "maio": 5,
    "junho": 6,
    "julho": 7,
    "agosto": 8,
    "setembro": 9,
    "outubro": 10,
    "novembro": 11,
    "dezembro": 12,
}


@dataclass(frozen=True)
class ResultadoSincronizacao:
    ano: int
    status: str
    alterado: bool
    quantidade_dias: int
    mensagem: str
    arquivo: str | None = None

    def como_dict(self) -> dict[str, object]:
        return asdict(self)


def _normalizar(valor: str) -> str:
    texto = unicodedata.normalize("NFKD", valor.strip().casefold())
    sem_acentos = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )
    return " ".join(sem_acentos.split())


def _cabecalho_do_ano(sopa: BeautifulSoup, ano: int) -> Tag | None:
    esperado = f"calendario do mercado {ano}"
    for tag in sopa.find_all(["h1", "h2", "h3"]):
        if _normalizar(tag.get_text(" ", strip=True)) == esperado:
            return tag
    return None


def extrair_calendario_b3(html: str, ano: int) -> CalendarioExtraido | None:
    """Extrai apenas fechamentos do segmento Listado B3."""
    sopa = BeautifulSoup(html, "lxml")
    cabecalho = _cabecalho_do_ano(sopa, ano)
    if cabecalho is None:
        return None

    datas: set[date] = set()
    linhas_hash: list[str] = []
    for tag in cabecalho.find_all_next(["h2", "a"]):
        texto_tag = _normalizar(tag.get_text(" ", strip=True))
        if (
            tag.name == "h2"
            and tag is not cabecalho
            and texto_tag.startswith("calendario do mercado ")
        ):
            break
        if tag.name != "a" or texto_tag not in MESES:
            continue
        destino = tag.get("href")
        if not isinstance(destino, str) or not destino.startswith("#"):
            continue
        painel = sopa.find(id=destino[1:])
        if not isinstance(painel, Tag):
            continue
        mes = MESES[texto_tag]
        for linha in painel.find_all("tr"):
            celulas = linha.find_all(["td", "th"])
            if len(celulas) < 2:
                continue
            dia_texto = _normalizar(celulas[0].get_text(" ", strip=True))
            if re.fullmatch(r"\d{1,2}", dia_texto) is None:
                continue
            texto_linha = _normalizar(linha.get_text(" ", strip=True))
            linhas_hash.append(f"{mes:02d}|{texto_linha}")
            fechamento_listado = (
                "listado b3" in texto_linha
                and (
                    "nao havera negociacao nos mercados de renda variavel"
                    in texto_linha
                )
            )
            if fechamento_listado:
                datas.add(date(ano, mes, int(dia_texto)))

    if not linhas_hash:
        raise ValueError(f"A seção B3 de {ano} não contém tabelas reconhecíveis.")
    if not datas:
        raise ValueError(f"Nenhum fechamento do Listado B3 foi extraído em {ano}.")
    canonico = "\n".join(linhas_hash)
    return CalendarioExtraido(
        ano=ano,
        datas=tuple(sorted(datas)),
        hash_conteudo=hashlib.sha256(canonico.encode()).hexdigest(),
    )


def _diretorio_cache() -> Path:
    personalizado = os.getenv("RECOMENDADOR_CALENDARIOS_CACHE_DIR")
    if personalizado:
        return Path(personalizado).expanduser()
    return (
        Path.home()
        / ".cache"
        / "recomendador_investimentos"
        / "calendarios"
        / "b3"
    )


def _json_existente(ano: int) -> dict[str, object] | None:
    candidatos = [
        _diretorio_cache() / f"{ano}.json",
        Path(__file__).with_name("b3") / f"{ano}.json",
    ]
    for arquivo in candidatos:
        if arquivo.exists():
            try:
                dados = json.loads(arquivo.read_text(encoding="utf-8"))
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(dados, dict) and dados.get("ano") == ano:
                return dados
    return None


def _salvar_atomicamente(payload: dict[str, object], ano: int) -> Path:
    diretorio = _diretorio_cache()
    diretorio.mkdir(parents=True, exist_ok=True)
    destino = diretorio / f"{ano}.json"
    if destino.exists():
        shutil.copy2(destino, destino.with_suffix(".json.bak"))
    descritor, temporario = tempfile.mkstemp(
        prefix=f".{ano}.",
        suffix=".tmp",
        dir=diretorio,
    )
    try:
        with os.fdopen(descritor, "w", encoding="utf-8") as arquivo:
            json.dump(payload, arquivo, ensure_ascii=False, indent=2)
            arquivo.write("\n")
            arquivo.flush()
            os.fsync(arquivo.fileno())
        os.replace(temporario, destino)
    except OSError:
        Path(temporario).unlink(missing_ok=True)
        raise
    return destino


def _sincronizar_extraido(
    calendario: CalendarioExtraido,
    *,
    fonte: str,
    ultima_modificacao: str | None,
) -> ResultadoSincronizacao:
    existente = _json_existente(calendario.ano) or {}
    datas_iso = [item.isoformat() for item in calendario.datas]
    sem_alteracao = existente.get("dias_sem_negociacao") == datas_iso
    payload: dict[str, object] = {
        "ano": calendario.ano,
        "status": "confirmado",
        "verificado_em": datetime.now(UTC).isoformat(),
        "fonte": fonte,
        "fonte_ultima_modificacao": ultima_modificacao,
        "hash_fonte": calendario.hash_conteudo,
        "dias_sem_negociacao": datas_iso,
    }
    arquivo = _salvar_atomicamente(payload, calendario.ano)

    from calendarios.mercado import carregar_ano  # evita importação circular

    carregar_ano.cache_clear()
    return ResultadoSincronizacao(
        ano=calendario.ano,
        status="sem_alteracao" if sem_alteracao else "atualizado",
        alterado=not sem_alteracao,
        quantidade_dias=len(calendario.datas),
        mensagem=(
            "Calendário oficial conferido; não houve mudança."
            if sem_alteracao
            else "Calendário oficial validado e substituído atomicamente."
        ),
        arquivo=str(arquivo),
    )


def sincronizar_calendarios_relevantes(
    *,
    data_referencia: date | None = None,
    sessao: requests.Session | None = None,
) -> tuple[ResultadoSincronizacao, ...]:
    """Verifica automaticamente o ano atual e o seguinte em uma única chamada."""
    referencia = data_referencia or datetime.now(
        ZoneInfo("America/Sao_Paulo")
    ).date()
    anos = (referencia.year, referencia.year + 1)
    cliente = sessao or requests.Session()
    try:
        resposta = cliente.get(
            URL_CALENDARIO_B3,
            timeout=(3.05, 12),
            headers={
                "User-Agent": (
                    "recomendador-investimentos/1.0 "
                    "(+verificacao-calendario-b3)"
                )
            },
        )
        resposta.raise_for_status()
        if not fonte_b3_oficial(str(resposta.url)):
            raise ValueError("A consulta foi redirecionada para domínio não oficial.")
    except (requests.RequestException, ValueError) as exc:
        return tuple(
            ResultadoSincronizacao(
                ano=ano,
                status="fonte_indisponivel",
                alterado=False,
                quantidade_dias=0,
                mensagem=f"Fonte B3 indisponível; cache preservado: {exc}",
            )
            for ano in anos
        )

    resultados: list[ResultadoSincronizacao] = []
    for ano in anos:
        try:
            calendario = extrair_calendario_b3(resposta.text, ano)
            if calendario is None:
                resultados.append(
                    ResultadoSincronizacao(
                        ano=ano,
                        status="nao_publicado",
                        alterado=False,
                        quantidade_dias=0,
                        mensagem="A B3 ainda não publicou a seção anual.",
                    )
                )
                continue
            validar_calendario_extraido(
                calendario,
                anos_permitidos=anos,
            )
            resultados.append(
                _sincronizar_extraido(
                    calendario,
                    fonte=str(resposta.url),
                    ultima_modificacao=resposta.headers.get("Last-Modified"),
                )
            )
        except (OSError, TypeError, ValueError) as exc:
            resultados.append(
                ResultadoSincronizacao(
                    ano=ano,
                    status="rejeitado",
                    alterado=False,
                    quantidade_dias=0,
                    mensagem=f"Novo conteúdo rejeitado; cache preservado: {exc}",
                )
            )
    return tuple(resultados)


def main() -> None:
    """Executa a sincronização sob demanda e imprime um resumo auditável."""
    resultados = sincronizar_calendarios_relevantes()
    print(
        json.dumps(
            [resultado.como_dict() for resultado in resultados],
            ensure_ascii=False,
            indent=2,
        )
    )
    if any(
        resultado.status in {"fonte_indisponivel", "rejeitado"}
        for resultado in resultados
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
