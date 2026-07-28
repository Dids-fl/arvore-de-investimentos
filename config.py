import os
from dotenv import load_dotenv

load_dotenv()

# ── Alíquotas de IR ───────────────────────────────────────────────────────────
IR_RF    = 0.15
IR_ACOES = 0.15
IR_VGBL  = 0.10
IR_PGBL  = 0.10
IR_LCI   = 0.00
IR_FII   = 0.10

# ── Configurações de timeout e retry ────────────────────────────────────────────
# NOTA: este projeto não usa taxas fixas de fallback (SELIC/IPCA/IBOV).
# Se as fontes online (BCB/SGS, Focus, Yahoo Finance) estiverem indisponíveis,
# `mercado.load_market_data()` levanta `DadosIndisponiveisError` em vez de
# substituir por um número hardcoded — ver utils/exceptions.py.
REQUEST_TIMEOUT = (5.0, 10.0)   # connect, read
MAX_RETRIES = 3
RETRY_BACKOFF = 0.5

# ── Chaves de API (opcionais) ────────────────────────────────────────────────────
BRAPI_TOKEN = os.getenv("BRAPI_TOKEN")
FMP_API_KEY = os.getenv("FMP_API_KEY")

# ── Filtros opcionais para ações ────────────────────────────────────────────────
USE_FUNDAMENTUS = True   # Se True, tenta enriquecer com dados do Fundamentus
FILTRO_SETORES = []      # Ex: ["Financeiro", "Petróleo"] – vazio = sem filtro
FILTRO_GOVERNANCA = []   # Ex: ["NM", "N2"] – vazio = sem filtro

# ── Filtros de Market Cap para ações (NOVO) ────────────────────────────────────
# Mínimo de market cap (em reais) por perfil de risco
LIMITE_MKTCAP = {
    1: 2_000_000_000,
    2: 1_000_000_000,
    3: 500_000_000,
}