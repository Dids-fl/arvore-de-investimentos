import unicodedata
from typing import Optional, Dict, List

# ── Normalização de texto ─────────────────────────────────────────────────────

def _nrm(s: str) -> str:
    """Remove acentos, espaços extras, coloca em minúsculas."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.strip().lower()


# ── Funções de input interativo ───────────────────────────────────────────────

def _p(q: str, ops: dict):
    ops_nrm = {_nrm(k): v for k, v in ops.items()}
    while True:
        print("\n" + q)
        r = _nrm(input("   → "))
        if r in ops_nrm:
            return ops_nrm[r]
        print("   ❌ Opção inválida. Tente novamente.")


def _p_primeira(q: str, ops: dict):
    ops_nrm = {_nrm(k): v for k, v in ops.items()}
    while True:
        print("\n" + q)
        r = _nrm(input("   → "))
        if r == "d":
            return "__DEMO__"
        if r in ops_nrm:
            return ops_nrm[r]
        print("   ❌ Opção inválida. Tente novamente.")


def _n(q: str, mn: float = 0, mx: Optional[float] = None,
       opt: bool = False) -> Optional[float]:
    while True:
        print("\n" + q)
        if opt:
            print("   (Enter para pular)")
        e = input("   → ").strip().replace(",", ".")
        if opt and e == "":
            return None
        try:
            v = float(e)
            if v < mn:
                print(f"   ❌ Mínimo: {mn}")
                continue
            if mx is not None and v > mx:
                print(f"   ❌ Máximo: {mx}")
                continue
            return v
        except ValueError:
            print("   ❌ Número inválido.")


_EXP_CANON: Dict[str, str] = {
    "poupanca": "poupança", "poupança": "poupança",
    "tesouro":  "tesouro",
    "acoes":    "ações",    "ações":    "ações",
    "fundos":   "fundos",
    "opcoes":   "opções",   "opções":   "opções",
    "nenhum":   "nenhum",
}


def _m(q: str) -> List[str]:
    while True:
        print("\n" + q)
        e = input("   → ").strip()
        cs_raw = [x.strip() for x in e.split(",")]
        cs_nrm = [_nrm(c) for c in cs_raw]
        inv = [cs_raw[i] for i, n in enumerate(cs_nrm) if n not in _EXP_CANON]
        if inv:
            print(f"   ❌ Inválidos: {inv}")
        else:
            return [_EXP_CANON[n] for n in cs_nrm]


def _sep():
    print("\n" + "─" * 58)


# ── Dicionários de opções do questionário ─────────────────────────────────────

_PD  = {"curto": 1, "médio": 2, "medio": 2, "longo": 3}
_RD  = {"baixo": 1, "médio": 2, "medio": 2, "alto": 3}
_OD  = {"reserva": 1, "crescimento": 2, "aposentadoria": 3}
_FD  = {"renda": 1, "acúmulo": 2, "acumulo": 2}
_CD  = {"gerir": 1, "delegar": 2}
_LD  = {"sim": 1, "não": 2, "nao": 2}
_RSD = {"não tenho": 1, "nao tenho": 1, "parcial": 2, "sim": 3}
_ID  = {"jovem": 1, "adulto": 2, "sênior": 3, "senior": 3}
_DD  = {"nenhuma": 1, "baixas": 2, "altas": 3}
_VD  = {"baixo": 1, "médio": 2, "medio": 2, "alto": 3}
_PPD = {"baixo": 1, "médio": 2, "medio": 2, "alto": 3}
_RND = {"clt": 1, "pj contratado": 2, "pj": 2, "autônomo": 3, "autonomo": 3, "sem renda": 4}
_DVd = {"juros altos": 1, "juros baixos": 2, "não tenho": 3, "nao tenho": 3}
_KD  = {"iniciante": 1, "intermediário": 2, "intermediario": 2, "experiente": 3}
_DPD = {"nenhum": 1, "um": 2, "dois ou mais": 3}
_APD = {"único": 1, "unico": 1, "mensal": 2}
_EMD = {"venderia tudo": 1, "esperaria recuperar": 2, "compraria mais": 3}
_IRD = {"completo": 1, "simplificado": 2, "não declaro": 3, "nao declaro": 3}
_CAD = {"não tenho": 1, "nao tenho": 1, "conservadora": 2, "moderada": 3, "arrojada": 4}
_MTD = {"sim": 1, "rendendo": 2, "não": 3, "nao": 3}

# ── Perfil de demonstração ────────────────────────────────────────────────────

DEMO_PADRAO = {
    "prazo":        3,
    "risco":        2,
    "objetivo":     2,
    "fluxo":        1,
    "controle":     1,
    "liquidez":     2,
    "liquidez_pct": 0.0,
    "reserva_emerg":1,
    "idade":        1,
    "despesas":     1,
    "faixa_valor":  2,
    "patrim_pct":   3,
    "renda":        4,
    "dividas":      3,
    "conhecimento": 1,
    "experiencia":  ["nenhum"],
    "dependentes":  1,
    "aporte":       1,
    "emocional":    2,
    "ir_tipo":      3,
    "carteira_atual":1,
    "modo_meta":    2,
    "cap_inicial":  6000.0,
    "aporte_mensal":0.0,
}