import logging
import sys

def setup_logging(level=logging.INFO):
    """Configura o logging para a aplicação."""
    root = logging.getLogger()
    root.setLevel(level)
    
    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(level)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
    
    # Suprime logs excessivos de bibliotecas externas
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("yfinance").setLevel(logging.WARNING)

def get_logger(name: str):
    return logging.getLogger(name)