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
            "SELECT * FROM atividades WHERE id = ?",
            (atividade_id,),
        ).fetchone()


def cadastrar_atividade(dados):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO atividades (nome, pontos, descricao, ativo)
            VALUES (?, ?, ?, ?)
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
            SET nome = ?, pontos = ?, descricao = ?, ativo = ?
            WHERE id = ?
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
        connection.execute("DELETE FROM atividades WHERE id = ?", (atividade_id,))


def listar_cumprimentos(adolescente_id=None):
    parametros = []
    filtro = ""
    if adolescente_id:
        filtro = "WHERE ct.adolescente_id = ?"
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
            WHERE id = ?
            """,
            (cumprimento_id,),
        ).fetchone()


def registrar_cumprimento(dados):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO cumprimentos_tarefas (
                adolescente_id, atividade_id, data_cumprimento, cumpriu, observacoes
            ) VALUES (?, ?, ?, ?, ?)
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
            ) VALUES (?, ?, ?, ?, ?)
            """,
            registros,
        )


def atualizar_cumprimento(cumprimento_id, dados):
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE cumprimentos_tarefas
            SET adolescente_id = ?, atividade_id = ?, data_cumprimento = ?, cumpriu = ?, observacoes = ?
            WHERE id = ?
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
        connection.execute("DELETE FROM cumprimentos_tarefas WHERE id = ?", (cumprimento_id,))


def listar_presencas(adolescente_id=None):
    parametros = []
    filtro = ""
    if adolescente_id:
        filtro = "WHERE p.adolescente_id = ?"
        parametros.append(adolescente_id)

    with get_connection() as connection:
        return connection.execute(
            f"""
            SELECT
                p.*,
                ad.nome AS adolescente_nome,
                ad.matricula AS adolescente_matricula
            FROM presencas p
            JOIN adolescentes ad ON ad.id = p.adolescente_id
            {filtro}
            ORDER BY p.data_presenca DESC, p.id DESC
            """,
            parametros,
        ).fetchall()


def obter_presenca(presenca_id):
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM presencas WHERE id = ?",
            (presenca_id,),
        ).fetchone()


def registrar_presenca(dados):
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO presencas (
                adolescente_id, data_presenca, presente, pontos, observacoes
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(dados["adolescente_id"]),
                dados["data_presenca"],
                int(dados["presente"]),
                int(dados["pontos"]),
                dados.get("observacoes", "").strip(),
            ),
        )


def atualizar_presenca(presenca_id, dados):
    with get_connection() as connection:
        connection.execute(
            """
            UPDATE presencas
            SET adolescente_id = ?, data_presenca = ?, presente = ?, pontos = ?, observacoes = ?
            WHERE id = ?
            """,
            (
                int(dados["adolescente_id"]),
                dados["data_presenca"],
                int(dados["presente"]),
                int(dados["pontos"]),
                dados.get("observacoes", "").strip(),
                presenca_id,
            ),
        )


def excluir_presenca(presenca_id):
    with get_connection() as connection:
        connection.execute("DELETE FROM presencas WHERE id = ?", (presenca_id,))
