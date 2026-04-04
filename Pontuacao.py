from database import get_connection


def ranking_geral():
    with get_connection() as connection:
        return connection.execute(
            """
            WITH pontos_tarefas AS (
                SELECT
                    ct.adolescente_id,
                    SUM(CASE WHEN ct.cumpriu = 1 THEN a.pontos ELSE 0 END) AS total_tarefas
                FROM cumprimentos_tarefas ct
                JOIN atividades a ON a.id = ct.atividade_id
                GROUP BY ct.adolescente_id
            )
            SELECT
                ad.id,
                ad.matricula,
                ad.nome,
                ad.sexo,
                ad.lider_ga,
                COALESCE(pt.total_tarefas, 0) AS pontos_tarefas,
                COALESCE(pt.total_tarefas, 0) AS total_pontos
            FROM adolescentes ad
            LEFT JOIN pontos_tarefas pt ON pt.adolescente_id = ad.id
            ORDER BY total_pontos DESC, ad.nome
            """
        ).fetchall()


def ranking_por_sexo():
    ranking = ranking_geral()
    resultado = {"M": [], "F": []}

    for item in ranking:
        sexo = item["sexo"]
        if sexo in resultado:
            resultado[sexo].append(item)

    return resultado


def ranking_por_lider_ga():
    with get_connection() as connection:
        return connection.execute(
            """
            WITH pontos_tarefas AS (
                SELECT
                    ct.adolescente_id,
                    SUM(CASE WHEN ct.cumpriu = 1 THEN a.pontos ELSE 0 END) AS total_tarefas
                FROM cumprimentos_tarefas ct
                JOIN atividades a ON a.id = ct.atividade_id
                GROUP BY ct.adolescente_id
            )
            SELECT
                ad.lider_ga,
                COUNT(ad.id) AS total_adolescentes,
                COALESCE(SUM(COALESCE(pt.total_tarefas, 0)), 0) AS total_pontos
            FROM adolescentes ad
            LEFT JOIN pontos_tarefas pt ON pt.adolescente_id = ad.id
            GROUP BY ad.lider_ga
            ORDER BY total_pontos DESC, ad.lider_ga
            """
        ).fetchall()


def ranking_lideres_mais_ativos():
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT
                u.id,
                u.nome,
                u.username,
                u.role,
                COALESCE(u.lider_ga, '-') AS lider_ga,
                COUNT(ae.id) AS total_acoes,
                COUNT(*) FILTER (WHERE ae.tipo_evento = 'cadastro_adolescente') AS adolescentes_cadastrados,
                COUNT(*) FILTER (WHERE ae.tipo_evento = 'edicao_adolescente') AS adolescentes_editados,
                COUNT(*) FILTER (WHERE ae.tipo_evento = 'lancamento_cumprimento') AS cumprimentos_lancados,
                COUNT(*) FILTER (WHERE ae.tipo_evento = 'edicao_cumprimento') AS cumprimentos_editados
            FROM usuarios u
            LEFT JOIN auditoria_eventos ae
                ON ae.usuario_id = u.id
                AND ae.tipo_evento IN (
                    'cadastro_adolescente',
                    'edicao_adolescente',
                    'lancamento_cumprimento',
                    'edicao_cumprimento'
                )
            WHERE u.aprovado = 1
            GROUP BY u.id, u.nome, u.username, u.role, u.lider_ga
            ORDER BY total_acoes DESC, u.nome
            """
        ).fetchall()


def resumo_dashboard():
    ranking = ranking_geral()
    ranking_atividade = ranking_lideres_mais_ativos()

    total_adolescentes = len(ranking)
    total_pontos = sum(item["total_pontos"] for item in ranking)
    lideres_ga = sorted({item["lider_ga"] for item in ranking if item["lider_ga"]})

    top_5 = ranking[:5]

    return {
        "total_adolescentes": total_adolescentes,
        "total_pontos": total_pontos,
        "lideres_ga": lideres_ga,
        "top_5": top_5,
        "ranking_lider_ga": ranking_por_lider_ga()[:5],
        "lideres_mais_ativos": ranking_atividade[:5],
    }
