from screener import top_acoes

def test_top_acoes():
    # Teste básico para ver se retorna lista (pode falhar se API estiver fora)
    resultado = top_acoes(perfil=2, n=3)
    assert isinstance(resultado, list)
    # Não testamos conteúdo para não depender da API