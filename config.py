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

# ── Taxas de fallback (usadas quando as APIs estão indisponíveis) ─────────────
FB_SELIC = 0.1075
FB_IPCA  = 0.0450
FB_IBOV  = 0.09

# ── Configurações de timeout e retry ────────────────────────────────────────────
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