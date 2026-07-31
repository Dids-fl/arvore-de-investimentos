# produtos_estruturados/cadastro_coletor.py
"""
Coleta o cadastro de Produtos Estruturados (CRA, CRI, Debêntures) via
mercados.b3.B3 (PythonicCafe/mercados).

Cadastro muda pouco (novas emissões são esporádicas), então cacheamos
localmente em JSON e só re-buscamos após TTL_HORAS, no mesmo espírito do
fundos/cvm_cadastro_downloader.py.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from mercados.b3 import B3

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
CADASTRO_PATH = DATA_DIR / "cadastro_estruturados.json"

TTL_HORAS = 24 * 7  # cadastro é atualizado semanalmente


def _garantir_pasta():
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def _cache_valido():
    if not CADASTRO_PATH.exists():
        return False
    idade = datetime.now(timezone.utc).timestamp() - CADASTRO_PATH.stat().st_mtime
    return idade < TTL_HORAS * 3600


def _coletar_securitizadoras(b3: B3):
    """
    Lista as securitizadoras cadastradas na B3 (emissoras de CRA/CRI).

    Atenção: o próprio código da lib `mercados` sinaliza que este endpoint
    pode estar desatualizado (a página de origem foi migrada em algum
    momento). Por isso, qualquer falha aqui não deve interromper a coleta
    de debêntures, que usa uma rota independente.
    """
    try:
        return list(b3.securitizadoras())
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Falha ao coletar securitizadoras (endpoint pode estar desatualizado): {e}")
        return []


def _coletar_cras_cris(b3: B3, securitizadoras):
    cras, cris = [], []
    for sec in securitizadoras:
        cnpj = sec.get("cnpj") or sec.get("CNPJ")
        if not cnpj:
            continue
        try:
            for cra in b3.cras(cnpj):
                cra["_securitizadora_cnpj"] = cnpj
                cra["_tipo"] = "CRA"
                cras.append(cra)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Falha ao coletar CRAs da securitizadora %s: %s",
                cnpj,
                e,
            )
        try:
            for cri in b3.cris(cnpj):
                cri["_securitizadora_cnpj"] = cnpj
                cri["_tipo"] = "CRI"
                cris.append(cri)
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Falha ao coletar CRIs da securitizadora %s: %s",
                cnpj,
                e,
            )
    return cras, cris


def _coletar_debentures(b3: B3):
    try:
        debentures = list(b3.debentures())
        for d in debentures:
            d["_tipo"] = "DEBENTURE"
        return debentures
    except Exception as e:  # noqa: BLE001
        logger.error("Falha ao coletar debêntures: %s", e)
        return []


def _baixar_cadastro():
    logger.info("Baixando cadastro de Produtos Estruturados (CRA/CRI/Debêntures)...")
    b3 = B3()

    securitizadoras = _coletar_securitizadoras(b3)
    logger.info(f"Securitizadoras encontradas: {len(securitizadoras)}")
    if not securitizadoras:
        logger.warning(
            "securitizadoras() retornou vazio SEM lançar exceção — isso pode "
            "ser instabilidade pontual da rede da B3 (mesmo com o patch "
            "aplicado) em vez de um erro de código. Tente rodar de novo."
        )
    cras, cris = _coletar_cras_cris(b3, securitizadoras)
    debentures = _coletar_debentures(b3)

    cadastro = {
        "atualizado_em": datetime.now(timezone.utc).isoformat(),
        "securitizadoras": securitizadoras,
        "cras": cras,
        "cris": cris,
        "debentures": debentures,
    }

    _garantir_pasta()
    with open(CADASTRO_PATH, "w", encoding="utf-8") as f:
        json.dump(cadastro, f, ensure_ascii=False, default=str)

    logger.info(
        f"Cadastro salvo: {len(cras)} CRAs, {len(cris)} CRIs, "
        f"{len(debentures)} debêntures."
    )
    return cadastro


def obter_cadastro(force=False):
    """API pública: retorna o cadastro (dict com 'cras', 'cris', 'debentures'),
    usando cache local quando possível."""
    if not force and _cache_valido():
        with open(CADASTRO_PATH, encoding="utf-8") as f:
            return json.load(f)
    return _baixar_cadastro()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s - %(message)s")
    cad = obter_cadastro(force=True)
    print(f"CRAs: {len(cad['cras'])} | CRIs: {len(cad['cris'])} | Debêntures: {len(cad['debentures'])}")