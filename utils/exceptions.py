"""
Exceções compartilhadas do projeto.

`DadosIndisponiveisError` deve ser usada em qualquer coletor/ranker sempre
que uma fonte de dado online (BCB, B3, CVM, BRAPI, CoinGecko, Fundamentus,
Yahoo Finance, Tesouro Nacional etc.) falhar ou não retornar dado válido.

Regra do projeto: NUNCA usar número fixo/hardcoded como substituto de um
dado que deveria vir de uma API. Se a fonte falhar, propague esta exceção
para que a camada de recomendação decida como comunicar isso ao usuário
(ex.: omitir a classe de ativo com um aviso claro), em vez de inventar
um valor.
"""


class DadosIndisponiveisError(Exception):
    """Levantada quando uma fonte de dado online está indisponível ou
    não retornou dado válido, e não há fallback fixo aceitável."""

    def __init__(self, fonte: str, detalhe: str = ""):
        self.fonte = fonte
        self.detalhe = detalhe
        msg = f"Dado indisponível: {fonte}"
        if detalhe:
            msg += f" — {detalhe}"
        super().__init__(msg)
