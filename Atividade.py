from database import get_connection


def listar_atividades(somente_ativas=False):
    filtro = "WHERE ativo = 1" if somente_ativas else ""
    with get_connection() as connection:
        return connection.execute(
            f"""
            SELECT *
            FROM atividades
            {filtro}
            ORDER BY ativo DESC, nome
            """
        ).fetchall()


def obter_atividade(atividade_id):
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM atividades WHERE id = %s",
            (atividade_id,),
        ).fetchone()


def cadastrar_atividade(dados):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO atividades (nome, pontos, descricao, ativo)
            VALUES (%s, %s, %s, %s)
            """,
            (
                dados["nome"].strip(),
                int(dados["pontos"]),
                dados.get("descricao", "").strip(),
                int(dados.get("ativo", 1)),
            ),
        )


def atualizar_atividade(atividade_id, dados):
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE atividades
            SET nome = %s, pontos = %s, descricao = %s, ativo = %s
            WHERE id = %s
            """,
            (
                dados["nome"].strip(),
                int(dados["pontos"]),
                dados.get("descricao", "").strip(),
                int(dados.get("ativo", 1)),
                atividade_id,
            ),
        )


def excluir_atividade(atividade_id):
    with get_connection() as connection:
        connection.execute("DELETE FROM atividades WHERE id = %s", (atividade_id,))


def listar_cumprimentos(adolescente_id=None):
    parametros = []
    filtro = ""
    if adolescente_id:
        filtro = "WHERE ct.adolescente_id = %s"
        parametros.append(adolescente_id)

    with get_connection() as connection:
        return connection.execute(
            f"""
            SELECT
                ct.*,
                a.nome AS atividade_nome,
                a.pontos AS atividade_pontos,
                ad.nome AS adolescente_nome,
                ad.matricula AS adolescente_matricula
            FROM cumprimentos_tarefas ct
            JOIN atividades a ON a.id = ct.atividade_id
            JOIN adolescentes ad ON ad.id = ct.adolescente_id
            {filtro}
            ORDER BY ct.data_cumprimento DESC, ct.id DESC
            """,
            parametros,
        ).fetchall()


def obter_cumprimento(cumprimento_id):
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT *
            FROM cumprimentos_tarefas
            WHERE id = %s
            """,
            (cumprimento_id,),
        ).fetchone()


def registrar_cumprimento(dados):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO cumprimentos_tarefas (
                adolescente_id, atividade_id, data_cumprimento, cumpriu, observacoes
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            (
                int(dados["adolescente_id"]),
                int(dados["atividade_id"]),
                dados["data_cumprimento"],
                int(dados["cumpriu"]),
                dados.get("observacoes", "").strip(),
            ),
        )


def registrar_cumprimentos_em_lote(dados, atividade_ids):
    registros = [
        (
            int(dados["adolescente_id"]),
            int(atividade_id),
            dados["data_cumprimento"],
            int(dados["cumpriu"]),
            dados.get("observacoes", "").strip(),
        )
        for atividade_id in atividade_ids
    ]

    with get_connection() as connection:
        connection.executemany(
            """
            INSERT INTO cumprimentos_tarefas (
                adolescente_id, atividade_id, data_cumprimento, cumpriu, observacoes
            ) VALUES (%s, %s, %s, %s, %s)
            """,
            registros,
        )


def atualizar_cumprimento(cumprimento_id, dados):
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE cumprimentos_tarefas
            SET adolescente_id = %s, atividade_id = %s, data_cumprimento = %s, cumpriu = %s, observacoes = %s
            WHERE id = %s
            """,
            (
                int(dados["adolescente_id"]),
                int(dados["atividade_id"]),
                dados["data_cumprimento"],
                int(dados["cumpriu"]),
                dados.get("observacoes", "").strip(),
                cumprimento_id,
            ),
        )


def excluir_cumprimento(cumprimento_id):
    with get_connection() as connection:
        connection.execute("DELETE FROM cumprimentos_tarefas WHERE id = %s", (cumprimento_id,))
